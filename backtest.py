"""Backtest cronológico conservador para archivos de velas exportadas."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from performance import PerformanceReport, analyze_pnls, format_report
from strategy import get_signal


REQUIRED_COLUMNS = {"from", "open", "close", "min", "max"}


@dataclass(frozen=True)
class BacktestResult:
    report: PerformanceReport
    pnls: tuple[float, ...]
    signal_times: tuple[int, ...]


def read_candles(path: Path) -> list[dict]:
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"Faltan columnas: {', '.join(sorted(missing))}")
        candles = []
        for row in reader:
            candles.append({
                "from": int(float(row["from"])),
                "open": float(row["open"]),
                "close": float(row["close"]),
                "min": float(row["min"]),
                "max": float(row["max"]),
            })
    return sorted(candles, key=lambda candle: candle["from"])


def run_backtest(
    candles: list[dict],
    *,
    strategy: str = "trend",
    payout: float = 0.82,
    stake: float = 1.0,
    expiration_bars: int = 1,
    cooldown_bars: int = 5,
    minimum_trades: int = 200,
    minimum_edge: float = 0.02,
    timeframe_seconds: int | None = None,
) -> BacktestResult:
    if not 0 < payout <= 1:
        raise ValueError("payout debe estar entre 0 y 1")
    if stake <= 0 or expiration_bars < 1 or cooldown_bars < 1:
        raise ValueError("stake, expiration_bars y cooldown_bars deben ser positivos")

    if timeframe_seconds is None and len(candles) >= 2:
        differences = [
            int(candles[index]["from"]) - int(candles[index - 1]["from"])
            for index in range(1, len(candles))
            if int(candles[index]["from"]) > int(candles[index - 1]["from"])
        ]
        timeframe_seconds = Counter(differences).most_common(1)[0][0] if differences else None

    pnls: list[float] = []
    signal_times: list[int] = []
    next_allowed_index = 60
    # En i solo existen las velas [0, i); la entrada ocurre en la apertura de i.
    for index in range(60, len(candles)):
        if index < next_allowed_index:
            continue
        # Producción solicita 80 velas; usar exactamente la misma ventana evita que
        # los indicadores se beneficien de una historia que el bot real no ve.
        signal = get_signal(candles[max(0, index - 105):index], strategy)
        if signal is None:
            continue
        signal_expiration_bars = expiration_bars
        if signal.expiration_min is not None:
            if timeframe_seconds != 60:
                continue
            signal_expiration_bars = signal.expiration_min
        if index + signal_expiration_bars > len(candles) or any(
            int(candles[position]["from"]) - int(candles[position - 1]["from"])
            != timeframe_seconds
            for position in range(index, index + signal_expiration_bars)
        ):
            continue
        entry = candles[index]["open"]
        exit_price = candles[index + signal_expiration_bars - 1]["close"]
        won = exit_price > entry if signal.direction == "call" else exit_price < entry
        # Un empate se trata como pérdida: evita favorecer artificialmente el resultado.
        pnl = stake * payout if won else -stake
        pnls.append(pnl)
        signal_times.append(signal.candle_time)
        next_allowed_index = index + cooldown_bars

    return BacktestResult(
        analyze_pnls(pnls, minimum_trades=minimum_trades, minimum_edge=minimum_edge),
        tuple(pnls), tuple(signal_times),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest sin look-ahead sobre velas OHLC.")
    parser.add_argument("candles_csv")
    parser.add_argument("--strategy", choices=("trend", "support_channel", "bollinger_reversal"), default="trend")
    parser.add_argument("--payout", type=float, required=True,
                        help="Ganancia neta por unidad arriesgada; por ejemplo 0.82")
    parser.add_argument("--stake", type=float, default=1.0)
    parser.add_argument("--expiration-bars", type=int, default=1)
    parser.add_argument("--cooldown-bars", type=int, default=5)
    parser.add_argument("--split", type=float, default=0.70,
                        help="Fracción inicial in-sample; el tramo final es fuera de muestra")
    parser.add_argument("--minimum-trades", type=int, default=200)
    parser.add_argument("--minimum-edge", type=float, default=0.02)
    args = parser.parse_args()
    if not 0.5 <= args.split < 1:
        raise ValueError("split debe estar entre 0.5 (incluido) y 1 (excluido)")

    candles = read_candles(Path(args.candles_csv))
    split_at = int(len(candles) * args.split)
    train = run_backtest(
        candles[:split_at], strategy=args.strategy, payout=args.payout, stake=args.stake,
        expiration_bars=args.expiration_bars, cooldown_bars=args.cooldown_bars,
        minimum_trades=args.minimum_trades, minimum_edge=args.minimum_edge,
        timeframe_seconds=None,
    )
    # Se conserva calentamiento previo, pero las señales reportadas empiezan en el corte.
    warmup_start = max(0, split_at - 80)
    test = run_backtest(
        candles[warmup_start:], strategy=args.strategy, payout=args.payout, stake=args.stake,
        expiration_bars=args.expiration_bars, cooldown_bars=args.cooldown_bars,
        minimum_trades=args.minimum_trades, minimum_edge=args.minimum_edge,
        timeframe_seconds=None,
    )
    test_pnls = [
        pnl for pnl, timestamp in zip(test.pnls, test.signal_times)
        if timestamp >= candles[split_at]["from"]
    ] if split_at < len(candles) else []
    out_of_sample = analyze_pnls(
        test_pnls, minimum_trades=args.minimum_trades, minimum_edge=args.minimum_edge
    )

    print("=== IN-SAMPLE (desarrollo) ===")
    print(format_report(train.report))
    print("\n=== OUT-OF-SAMPLE (decisión) ===")
    print(format_report(out_of_sample))
    print("\nLa decisión de avanzar debe basarse en OUT-OF-SAMPLE y confirmarse en PRACTICE.")


if __name__ == "__main__":
    main()
