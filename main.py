import csv
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from iqoptionapi.stable_api import IQ_Option
from config import Settings
from risk import RiskManager
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
    # Safety invariant: this project never selects REAL.
    client.change_balance("PRACTICE")
    log.info("Conectado exclusivamente a PRACTICE | saldo: %.2f", client.get_balance())
    return client


def main():
    cfg = Settings()
    cfg.validate()
    client = connect(cfg)
    risk = RiskManager(cfg.max_trades_day, cfg.max_consecutive_losses, cfg.max_daily_loss)
    last_signal_candle = None
    timeframe_seconds = cfg.timeframe_min * 60
    log.info("Activo=%s | monto=%.2f | trading=%s", cfg.asset, cfg.amount, cfg.enable_trading)

    while True:
        allowed, reason = risk.can_trade()
        if not allowed:
            log.warning("Bot detenido: %s | PnL=%.2f", reason, risk.pnl)
            break
        try:
            now = int(time.time())
            candles = client.get_candles(cfg.asset, timeframe_seconds, 80, now)
            # API may return the candle still forming; keep only definitely closed candles.
            closed = [c for c in candles if int(c["from"]) + timeframe_seconds <= now]
            signal = get_signal(closed)
            if signal and signal.candle_time != last_signal_candle:
                last_signal_candle = signal.candle_time
                log.info("SEÑAL %s | close=%.5f RSI=%.2f", signal.direction.upper(), signal.close, signal.rsi14)
                if cfg.enable_trading:
                    ok, order_id = client.buy(cfg.amount, cfg.asset, signal.direction, cfg.expiration_min)
                    if not ok:
                        log.error("Orden rechazada: %s", order_id)
                    else:
                        log.info("Orden PRACTICE enviada: %s", order_id)
                        pnl = float(client.check_win_v4(order_id))
                        risk.record(pnl)
                        save_trade(cfg.asset, signal, cfg.amount, order_id, pnl)
                        log.info("Resultado PnL=%.2f | diario=%.2f", pnl, risk.pnl)
            time.sleep(10)
        except KeyboardInterrupt:
            log.info("Detenido por el usuario")
            break
        except Exception as exc:
            log.exception("Error recuperable: %s", exc)
            time.sleep(15)
            if not client.check_connect():
                client = connect(cfg)


if __name__ == "__main__":
    main()
