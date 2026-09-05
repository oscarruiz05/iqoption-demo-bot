"""Descarga velas históricas sin enviar órdenes y las guarda para backtesting."""

from __future__ import annotations

import argparse
import csv
import logging
import time
from pathlib import Path

from iqoptionapi.stable_api import IQ_Option

from assets import parse_assets
from config import Settings


log = logging.getLogger("history-collector")
FIELDS = ("from", "open", "close", "min", "max", "volume")


def connect_read_only(settings: Settings):
    client = IQ_Option(settings.email, settings.password)
    ok, reason = client.connect()
    if not ok:
        raise ConnectionError(f"IQ Option rechazó la conexión: {reason}")
    return client


def fetch_candles(client, asset: str, timeframe_seconds: int, count: int) -> list[dict]:
    candles_by_time: dict[int, dict] = {}
    end_time = int(time.time())
    while len(candles_by_time) < count:
        batch_size = min(1000, count - len(candles_by_time))
        batch = client.get_candles(asset, timeframe_seconds, batch_size, end_time)
        if not batch:
            break
        now = int(time.time())
        for candle in batch:
            timestamp = int(candle["from"])
            if timestamp + timeframe_seconds <= now:
                candles_by_time[timestamp] = candle
        oldest = min(int(candle["from"]) for candle in batch)
        if oldest >= end_time:
            break
        end_time = oldest - 1
        time.sleep(0.25)
    return [candles_by_time[key] for key in sorted(candles_by_time)][-count:]


def write_candles(path: Path, candles: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for candle in candles:
            writer.writerow({field: candle.get(field, "") for field in FIELDS})
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Recolecta velas; nunca ejecuta operaciones.")
    parser.add_argument("--assets", help="Lista separada por comas; por defecto usa IQ_ASSETS")
    parser.add_argument("--candles", type=int, default=5000)
    parser.add_argument("--timeframe-min", type=int, choices=(1, 5, 15))
    parser.add_argument("--output-dir", default=str(Path(__file__).with_name("data")))
    args = parser.parse_args()
    if args.candles < 100:
        raise ValueError("Se requieren al menos 100 velas")

    settings = Settings()
    if not settings.email or not settings.password:
        raise ValueError("Completa IQ_EMAIL e IQ_PASSWORD en .env")
    assets = parse_assets(args.assets) if args.assets else settings.assets
    timeframe_min = args.timeframe_min or settings.timeframe_min
    output_dir = Path(args.output_dir)
    client = connect_read_only(settings)
    log.warning("Conexión de solo lectura: no se enviarán órdenes")

    for asset in assets:
        try:
            candles = fetch_candles(client, asset, timeframe_min * 60, args.candles)
            if not candles:
                log.warning("%s: sin datos", asset)
                continue
            path = output_dir / f"{asset}_{timeframe_min}m.csv"
            write_candles(path, candles)
            log.info("%s: %d velas guardadas en %s", asset, len(candles), path)
        except Exception as exc:
            log.warning("%s: no fue posible descargar (%s)", asset, exc)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    main()
