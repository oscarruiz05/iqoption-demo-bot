"""Compara unas pocas hipótesis predefinidas sin mirar el tramo de prueba final."""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from backtest import read_candles
from performance import analyze_pnls
from strategy import add_indicators


@dataclass(frozen=True)
class Candidate:
    family: str
    p1: float
    p2: float

    @property
    def name(self) -> str:
        return f"{self.family}(p1={self.p1:g},p2={self.p2:g})"


def candidates() -> list[Candidate]:
    result = []
    result += [Candidate("rsi_turn", threshold, max_range)
               for threshold in (30, 35, 40) for max_range in (1.5, 2.0)]
    result += [Candidate("bollinger_rejection", deviations, threshold)
               for deviations in (1.5, 2.0, 2.5) for threshold in (35, 40, 45)]
    result += [Candidate("streak_reversal", streak, threshold)
               for streak in (2, 3, 4) for threshold in (35, 40, 45)]
    result += [Candidate("trend_momentum", minimum_rsi, maximum_rsi)
               for minimum_rsi, maximum_rsi in ((50, 60), (52, 65), (55, 70))]
    return result


def prepare(path: Path) -> pd.DataFrame:
    frame = add_indicators(read_candles(path))
    candle_range = (frame["max"] - frame["min"]).clip(lower=1e-12)
    frame["body_ratio"] = (frame["close"] - frame["open"]).abs() / candle_range
    frame["close_position"] = (frame["close"] - frame["min"]) / candle_range
    frame["range_ratio"] = candle_range / candle_range.rolling(20).median().shift(1)
    frame["mean20"] = frame["close"].rolling(20).mean()
    frame["std20"] = frame["close"].rolling(20).std()
    frame["up"] = frame["close"] > frame["open"]
    frame["down"] = frame["close"] < frame["open"]
    return frame


def candidate_signals(frame: pd.DataFrame, candidate: Candidate) -> tuple[pd.Series, pd.Series]:
    up, down = frame["up"], frame["down"]
    rsi = frame["rsi14"]
    normal = frame["range_ratio"].between(0.5, 2.0)
    rejection_up = up & (frame["close_position"] >= 0.65) & (frame["body_ratio"] >= 0.2)
    rejection_down = down & (frame["close_position"] <= 0.35) & (frame["body_ratio"] >= 0.2)

    if candidate.family == "rsi_turn":
        threshold, max_range = candidate.p1, candidate.p2
        call = rejection_up & (rsi <= threshold) & (rsi > rsi.shift(1))
        put = rejection_down & (rsi >= 100 - threshold) & (rsi < rsi.shift(1))
        range_filter = frame["range_ratio"].between(0.5, max_range)
        return call & range_filter, put & range_filter

    if candidate.family == "bollinger_rejection":
        deviations, threshold = candidate.p1, candidate.p2
        lower = frame["mean20"] - deviations * frame["std20"]
        upper = frame["mean20"] + deviations * frame["std20"]
        call = rejection_up & (frame["min"] <= lower) & (rsi <= threshold)
        put = rejection_down & (frame["max"] >= upper) & (rsi >= 100 - threshold)
        return call & normal, put & normal

    if candidate.family == "streak_reversal":
        streak, threshold = int(candidate.p1), candidate.p2
        prior_down = pd.concat([down.shift(offset) for offset in range(1, streak + 1)], axis=1).all(axis=1)
        prior_up = pd.concat([up.shift(offset) for offset in range(1, streak + 1)], axis=1).all(axis=1)
        call = rejection_up & prior_down & (rsi <= threshold)
        put = rejection_down & prior_up & (rsi >= 100 - threshold)
        return call & normal, put & normal

    if candidate.family == "trend_momentum":
        minimum_rsi, maximum_rsi = candidate.p1, candidate.p2
        rising = frame["ema20"] > frame["ema20"].shift(5)
        falling = frame["ema20"] < frame["ema20"].shift(5)
        call = (
            (frame["ema20"] > frame["ema50"]) & rising & rejection_up
            & rsi.between(minimum_rsi, maximum_rsi)
        )
        put = (
            (frame["ema20"] < frame["ema50"]) & falling & rejection_down
            & rsi.between(100 - maximum_rsi, 100 - minimum_rsi)
        )
        return call & normal, put & normal

    raise ValueError(f"Familia desconocida: {candidate.family}")


def evaluate_segment(
    frame: pd.DataFrame,
    candidate: Candidate,
    start: int,
    end: int,
    *,
    payout: float,
    cooldown_bars: int,
    timeframe_seconds: int,
) -> list[float]:
    calls, puts = candidate_signals(frame, candidate)
    pnls = []
    next_allowed = start
    # La señal está en i; la operación simulada usa apertura y cierre de i+1.
    for index in range(max(start, 60), min(end, len(frame) - 1)):
        if index < next_allowed or not (calls.iloc[index] or puts.iloc[index]):
            continue
        if int(frame.iloc[index + 1]["from"] - frame.iloc[index]["from"]) != timeframe_seconds:
            continue
        entry = float(frame.iloc[index + 1]["open"])
        exit_price = float(frame.iloc[index + 1]["close"])
        won = exit_price > entry if calls.iloc[index] else exit_price < entry
        pnls.append(payout if won else -1.0)
        next_allowed = index + cooldown_bars
    return pnls


def main() -> None:
    parser = argparse.ArgumentParser(description="Investigación temporal con test final sellado.")
    parser.add_argument("files", nargs="+")
    parser.add_argument("--payout", type=float, default=0.82)
    parser.add_argument("--cooldown-bars", type=int, default=5)
    parser.add_argument("--timeframe-seconds", type=int, default=300)
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--reveal-test", action="store_true")
    args = parser.parse_args()
    frames = {Path(file).stem: prepare(Path(file)) for file in args.files}

    rankings = []
    for candidate in candidates():
        train, validation = [], []
        validation_by_asset = []
        for frame in frames.values():
            first_cut = int(len(frame) * 0.60)
            second_cut = int(len(frame) * 0.80)
            train += evaluate_segment(
                frame, candidate, 0, first_cut, payout=args.payout,
                cooldown_bars=args.cooldown_bars, timeframe_seconds=args.timeframe_seconds,
            )
            asset_validation = evaluate_segment(
                frame, candidate, first_cut, second_cut, payout=args.payout,
                cooldown_bars=args.cooldown_bars, timeframe_seconds=args.timeframe_seconds,
            )
            validation += asset_validation
            validation_by_asset.append(sum(asset_validation) / len(asset_validation)
                                       if asset_validation else -1.0)
        train_report = analyze_pnls(train, minimum_trades=1, minimum_edge=0)
        validation_report = analyze_pnls(validation, minimum_trades=1, minimum_edge=0)
        robustness = min(validation_by_asset)
        eligible = (
            len(train) >= 100 and len(validation) >= 50
            and train_report.expectancy > 0 and validation_report.expectancy > 0
        )
        score = validation_report.expectancy * math.sqrt(max(1, len(validation))) + robustness
        rankings.append((eligible, score, candidate, train_report, validation_report, robustness))

    rankings.sort(key=lambda item: (item[0], item[1]), reverse=True)
    print("Selección usa 0-60% para desarrollo y 60-80% para validación.")
    print("El 80-100% permanece sellado salvo que se indique --reveal-test.\n")
    for eligible, score, candidate, train, validation, robustness in rankings[:args.top]:
        print(
            f"{candidate.name} | elegible={eligible} | score={score:.3f} | "
            f"train n={train.trades} exp={train.expectancy:.4f} WR={train.win_rate:.2%} | "
            f"valid n={validation.trades} exp={validation.expectancy:.4f} "
            f"WR={validation.win_rate:.2%} | peor activo={robustness:.4f}"
        )

    if args.reveal_test:
        selected = next((item for item in rankings if item[0]), None)
        if selected is None:
            print("\nTEST NO REVELADO: ningún candidato cumplió los criterios previos.")
            return
        candidate = selected[2]
        test = []
        print(f"\nTEST FINAL, candidato fijado: {candidate.name}")
        for name, frame in frames.items():
            second_cut = int(len(frame) * 0.80)
            asset_pnls = evaluate_segment(
                frame, candidate, second_cut, len(frame), payout=args.payout,
                cooldown_bars=args.cooldown_bars, timeframe_seconds=args.timeframe_seconds,
            )
            report = analyze_pnls(asset_pnls, minimum_trades=1, minimum_edge=0)
            print(f"{name}: n={report.trades} exp={report.expectancy:.4f} WR={report.win_rate:.2%}")
            test += asset_pnls
        report = analyze_pnls(test, minimum_trades=200, minimum_edge=0.02)
        print(
            f"TOTAL TEST: n={report.trades} PnL={report.pnl:.2f} exp={report.expectancy:.4f} "
            f"WR={report.win_rate:.2%} Wilson95={report.wilson_low:.2%} "
            f"validada={report.validated}"
        )


if __name__ == "__main__":
    main()
