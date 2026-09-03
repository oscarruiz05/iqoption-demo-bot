import csv
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from iqoptionapi.stable_api import IQ_Option
from config import Settings
from risk import RiskManager, extract_pnl
from strategy import get_signal

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s",
                    handlers=[logging.StreamHandler(), logging.FileHandler("bot.log", encoding="utf-8")])
log = logging.getLogger("iq-demo-bot")


def save_trade(asset, signal, amount, order_id, pnl):
    path = Path("trades.csv")
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        if new:
            writer.writerow(["utc_time", "asset", "direction", "amount", "order_id", "pnl", "rsi14"])
        writer.writerow([datetime.now(timezone.utc).isoformat(), asset, signal.direction,
                         amount, order_id, pnl, round(signal.rsi14, 2)])


def connect(settings):
    client = IQ_Option(settings.email, settings.password)
    ok, reason = client.connect()
    if not ok:
        raise ConnectionError(f"IQ Option rechazo la conexion: {reason}")
    client.change_balance("PRACTICE")
    log.info("Conectado exclusivamente a PRACTICE | saldo: %.2f", client.get_balance())
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
    client = connect_with_retry(cfg)
    risk = RiskManager(cfg.max_trades_day, cfg.max_consecutive_losses, cfg.max_daily_loss)
    last_signal_candles = {asset: None for asset in cfg.assets}
    timeframe_seconds = cfg.timeframe_min * 60
    disabled_until = {asset: 0.0 for asset in cfg.assets}
    log.info("Configurados=%s | monto=%.2f | trading=%s", ", ".join(cfg.assets), cfg.amount, cfg.enable_trading)

    while True:
        allowed, reason = risk.can_trade()
        if not allowed:
            log.warning("Bot detenido: %s | PnL=%.2f", reason, risk.pnl)
            break
        try:
            for asset in cfg.assets:
                allowed, reason = risk.can_trade()
                if not allowed:
                    log.warning("Bot detenido: %s | PnL=%.2f", reason, risk.pnl)
                    return

                if time.monotonic() < disabled_until[asset]:
                    continue

                now = int(time.time())
                try:
                    candles = client.get_candles(asset, timeframe_seconds, 80, now)
                except Exception as asset_error:
                    if not client.check_connect():
                        raise ConnectionError("Conexion perdida consultando velas") from asset_error
                    disabled_until[asset] = time.monotonic() + 300
                    log.warning("%s | No disponible (%s); omitido durante 5 minutos",
                                asset, asset_error)
                    continue

                if not candles:
                    disabled_until[asset] = time.monotonic() + 300
                    log.warning("%s | Sin velas; omitido durante 5 minutos", asset)
                    continue

                closed = [c for c in candles if int(c["from"]) + timeframe_seconds <= now]
                signal = get_signal(closed)
                if signal and signal.candle_time != last_signal_candles[asset]:
                    last_signal_candles[asset] = signal.candle_time
                    log.info("%s | SEÑAL %s | close=%.5f RSI=%.2f", asset, signal.direction.upper(), signal.close, signal.rsi14)
                    if cfg.enable_trading:
                        ok, order_id = client.buy(cfg.amount, asset, signal.direction, cfg.expiration_min)
                        if not ok:
                            log.error("%s | Orden rechazada: %s", asset, order_id)
                        else:
                            log.info("%s | Orden PRACTICE enviada: %s", asset, order_id)
                            raw_result = client.check_win_v4(order_id)
                            pnl = extract_pnl(raw_result)
                            risk.record(pnl)
                            save_trade(asset, signal, cfg.amount, order_id, pnl)
                            log.info("%s | Resultado PnL=%.2f | diario=%.2f", asset, pnl, risk.pnl)
            time.sleep(10)
        except KeyboardInterrupt:
            log.info("Detenido por el usuario")
            break
        except Exception as exc:
            log.exception("Error recuperable: %s", exc)
            time.sleep(15)
            if not client.check_connect():
                try:
                    client = connect_with_retry(cfg)
                except ConnectionError as reconnect_error:
                    log.error("Reconexión agotada; se intentara nuevamente: %s", reconnect_error)
                    time.sleep(60)


if __name__ == "__main__":
    main()
