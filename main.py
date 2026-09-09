import csv
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from iqoptionapi.stable_api import IQ_Option
from assets import is_connection_error, next_asset_batch, rejection_cooldown_seconds
from config import Settings
from performance import analyze_pnls, format_report, read_trade_pnls
from payout import PayoutCache
from risk import extract_pnl, load_daily_risk
from strategy import STRATEGY_VERSIONS, get_signal

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s",
                    handlers=[logging.StreamHandler(), logging.FileHandler("bot.log", encoding="utf-8")])
log = logging.getLogger("iq-demo-bot")

TRADE_HEADERS = [
    "utc_time", "asset", "direction", "amount", "order_id", "pnl", "rsi14",
    "strategy", "strategy_version", "candle_time", "signal_close", "ema20", "ema50",
    "reason", "balance_after", "payout_ratio", "quoted_payout", "expiration_min",
]
TRADE_PATH = Path(__file__).with_name("trades.csv")


def ensure_trade_schema(path: Path) -> None:
    if not path.exists():
        return
    with path.open("r", newline="", encoding="utf-8") as file:
        rows = list(csv.reader(file))
    if not rows:
        return
    header = rows[0]
    missing = [column for column in TRADE_HEADERS if column not in header]
    if not missing:
        return
    migrated = [header + missing]
    for row in rows[1:]:
        if not row:
            continue
        defaults = {"strategy": "trend", "strategy_version": "legacy"}
        migrated.append(row + [defaults.get(column, "") for column in missing])
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as file:
        csv.writer(file).writerows(migrated)
    temporary.replace(path)


def save_trade(
    asset, signal, amount, order_id, pnl, balance_after=None, quoted_payout=None,
    expiration_min=None,
):
    path = TRADE_PATH
    ensure_trade_schema(path)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        if new:
            writer.writerow(TRADE_HEADERS)
        writer.writerow([
            datetime.now(timezone.utc).isoformat(), asset, signal.direction, amount,
            order_id, pnl, round(signal.rsi14, 2), signal.strategy,
            STRATEGY_VERSIONS[signal.strategy],
            signal.candle_time, signal.close, signal.ema20, signal.ema50, signal.reason,
            "" if balance_after is None else balance_after,
            pnl / amount if pnl > 0 else 0.0,
            "" if quoted_payout is None else quoted_payout,
            "" if expiration_min is None else expiration_min,
        ])


def connect(settings):
    client = IQ_Option(settings.email, settings.password)
    ok, reason = client.connect()
    if not ok:
        raise ConnectionError(f"IQ Option rechazo la conexion: {reason}")
    client.change_balance(settings.account)
    log.info("Conectado a %s | saldo: %.2f", settings.account, client.get_balance())
    return client


def connect_with_retry(settings, attempts=5):
    delay = 5
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return connect(settings)
        except Exception as exc:
            last_error = exc
            log.warning("Conexion fallida (%d/%d): %s", attempt, attempts, exc)
            if attempt < attempts:
                time.sleep(delay)
                delay = min(delay * 2, 30)
    raise ConnectionError(f"No fue posible reconectar tras {attempts} intentos: {last_error}")


def main():
    cfg = Settings()
    cfg.validate()
    if cfg.account == "REAL":
        log.warning("MODO REAL SELECCIONADO | las operaciones usan dinero real")
    client = connect_with_retry(cfg)
    payouts = PayoutCache(client)
    balance = float(client.get_balance())
    max_stake = balance * cfg.max_risk_per_trade_pct / 100
    if cfg.enable_trading and cfg.amount > max_stake:
        message = (
            f"IQ_AMOUNT={cfg.amount:g} arriesga más de {cfg.max_risk_per_trade_pct:g}% "
            f"del saldo ({max_stake:.2f})"
        )
        if cfg.account == "REAL":
            raise ValueError(message)
        if cfg.show_practice_risk_warnings:
            log.warning("PRACTICE | %s; se respeta el monto elegido por el usuario", message)
    percentage_daily_loss = balance * cfg.max_daily_loss_pct / 100
    if cfg.account == "REAL":
        effective_daily_loss = min(cfg.max_daily_loss, percentage_daily_loss)
    else:
        effective_daily_loss = cfg.max_daily_loss
        if cfg.show_practice_risk_warnings and cfg.max_daily_loss > percentage_daily_loss:
            log.warning(
                "PRACTICE | MAX_DAILY_LOSS=%.2f supera %.1f%% del saldo (%.2f); "
                "se respeta el límite absoluto elegido",
                cfg.max_daily_loss, cfg.max_daily_loss_pct, percentage_daily_loss,
            )
    if cfg.account == "REAL" and cfg.enable_trading and cfg.require_validation_for_real:
        version = STRATEGY_VERSIONS[cfg.strategy]
        recent_pnls = read_trade_pnls(
            TRADE_PATH, strategy=cfg.strategy, strategy_version=version
        )[-cfg.validation_min_trades:]
        report = analyze_pnls(
            recent_pnls,
            minimum_trades=cfg.validation_min_trades,
            minimum_edge=cfg.validation_min_edge,
        )
        if not report.validated:
            raise ValueError("Estrategia no habilitada para REAL:\n" + format_report(report))
    risk_timezone = ZoneInfo(cfg.risk_timezone)
    risk_day = datetime.now(risk_timezone).date()
    risk = load_daily_risk(
        TRADE_PATH, cfg.max_trades_day, cfg.max_consecutive_losses, effective_daily_loss,
        day=risk_day, day_timezone=risk_timezone,
    )
    last_signal_candles = {asset: None for asset in cfg.assets}
    timeframe_seconds = cfg.timeframe_min * 60
    disabled_until = {asset: 0.0 for asset in cfg.assets}
    next_trade_candle = {asset: 0 for asset in cfg.assets}
    asset_cursor = 0
    log.info("Cuenta=%s | configurados=%s | estrategia=%s | monto=%.2f | trading=%s",
             cfg.account, ", ".join(cfg.assets), cfg.strategy, cfg.amount, cfg.enable_trading)

    while True:
        current_day = datetime.now(risk_timezone).date()
        if current_day != risk_day:
            risk_day = current_day
            risk = load_daily_risk(
                TRADE_PATH, cfg.max_trades_day, cfg.max_consecutive_losses,
                effective_daily_loss, day=risk_day, day_timezone=risk_timezone,
            )
        if cfg.enable_trading:
            allowed, reason = risk.can_trade(cfg.amount)
            if not allowed:
                log.warning("Bot detenido: %s | PnL=%.2f", reason, risk.pnl)
                break
        try:
            if not client.check_connect():
                raise ConnectionError("WebSocket desconectado antes de consultar velas")
            asset_batch, asset_cursor = next_asset_batch(
                cfg.assets, asset_cursor, cfg.asset_batch_size
            )
            for asset in asset_batch:
                if cfg.enable_trading:
                    allowed, reason = risk.can_trade(cfg.amount)
                    if not allowed:
                        log.warning("Bot detenido: %s | PnL=%.2f", reason, risk.pnl)
                        return
                if time.monotonic() < disabled_until[asset]:
                    continue
                now = int(time.time())
                try:
                    candles = client.get_candles(asset, timeframe_seconds, 80, now)
                    if cfg.asset_request_delay_seconds:
                        time.sleep(cfg.asset_request_delay_seconds)
                except Exception as asset_error:
                    if is_connection_error(asset_error) or not client.check_connect():
                        raise ConnectionError(
                            f"Conexion perdida consultando velas de {asset}"
                        ) from asset_error
                    disabled_until[asset] = time.monotonic() + 300
                    log.warning("%s | No disponible (%s); omitido durante 5 minutos",
                                asset, asset_error)
                    continue
                if not candles:
                    disabled_until[asset] = time.monotonic() + 300
                    log.warning("%s | Sin velas; omitido durante 5 minutos", asset)
                    continue
                closed = [c for c in candles if int(c["from"]) + timeframe_seconds <= now]
                signal = get_signal(closed, cfg.strategy)
                if signal and signal.candle_time != last_signal_candles[asset]:
                    last_signal_candles[asset] = signal.candle_time
                    if signal.candle_time < next_trade_candle[asset]:
                        log.info("%s | Señal omitida por espera entre operaciones", asset)
                        continue
                    expiration_min = signal.expiration_min or cfg.expiration_min
                    log.info(
                        "%s | %s | SEÑAL %s | close=%.5f RSI=%.2f | expiración=%dm",
                        asset, signal.strategy, signal.direction.upper(), signal.close,
                        signal.rsi14, expiration_min,
                    )
                    if cfg.enable_trading:
                        try:
                            quoted_payout = payouts.get(asset, expiration_min)
                        except Exception as payout_error:
                            log.warning("%s | No se pudo consultar payout; operación omitida: %s",
                                        asset, payout_error)
                            continue
                        if quoted_payout is None or quoted_payout < cfg.min_payout:
                            shown = "no disponible" if quoted_payout is None else f"{quoted_payout:.0%}"
                            log.info("%s | Payout %s inferior al mínimo %.0f%%; señal omitida",
                                     asset, shown, cfg.min_payout * 100)
                            continue
                        ok, order_id = client.buy(
                            cfg.amount, asset, signal.direction, expiration_min
                        )
                        if not ok:
                            cooldown = rejection_cooldown_seconds(order_id)
                            disabled_until[asset] = time.monotonic() + cooldown
                            log.warning("%s | Orden rechazada: %s | omitido %d minutos",
                                        asset, order_id, cooldown // 60)
                        else:
                            log.info("%s | Orden %s enviada: %s", asset, cfg.account, order_id)
                            raw_result = client.check_win_v4(order_id)
                            pnl = extract_pnl(raw_result)
                            risk.record(pnl)
                            next_trade_candle[asset] = (
                                signal.candle_time
                                + cfg.min_candles_between_trades * timeframe_seconds
                            )
                            try:
                                balance_after = float(client.get_balance())
                            except Exception:
                                balance_after = None
                            save_trade(
                                asset, signal, cfg.amount, order_id, pnl, balance_after,
                                quoted_payout, expiration_min,
                            )
                            log.info("%s | Resultado PnL=%.2f | diario=%.2f", asset, pnl, risk.pnl)
            time.sleep(10)
        except KeyboardInterrupt:
            log.info("Detenido por el usuario")
            break
        except Exception as exc:
            log.exception("Error recuperable: %s", exc)
            reconnect_required = isinstance(exc, ConnectionError)
            if not reconnect_required:
                try:
                    reconnect_required = not client.check_connect()
                except Exception:
                    reconnect_required = True
            if reconnect_required:
                time.sleep(5)
                try:
                    client = connect_with_retry(cfg)
                    payouts = PayoutCache(client)
                    log.info("Conexion restablecida; se reanuda el escaneo por lotes")
                except ConnectionError as reconnect_error:
                    log.error("Reconexión agotada; se intentara nuevamente: %s", reconnect_error)
                    time.sleep(60)
            else:
                time.sleep(15)


if __name__ == "__main__":
    main()
