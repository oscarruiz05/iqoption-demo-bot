"""Modelo direccional regularizado con división temporal y test final sellado."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from backtest import read_candles
from performance import PerformanceReport, analyze_pnls
from strategy import add_indicators


FEATURES = (
    "ema_spread_atr", "ema_slope_atr", "rsi_centered", "body_atr",
    "range_atr", "close_position", "return_1_atr", "return_2_atr",
    "return_3_atr", "hour_sin", "hour_cos",
)


@dataclass(frozen=True)
class Dataset:
    x_train: np.ndarray
    y_train: np.ndarray
    x_validation: np.ndarray
    y_validation: np.ndarray
    x_test: np.ndarray
    y_test: np.ndarray


def _features(path: Path, timeframe_seconds: int) -> pd.DataFrame:
    frame = add_indicators(read_candles(path))
    atr = frame["atr14"].replace(0, np.nan)
    timestamp = pd.to_datetime(frame["from"], unit="s", utc=True)
    candle_range = frame["max"] - frame["min"]
    frame["ema_spread_atr"] = (frame["ema20"] - frame["ema50"]) / atr
    frame["ema_slope_atr"] = (frame["ema20"] - frame["ema20"].shift(5)) / atr
    frame["rsi_centered"] = (frame["rsi14"] - 50) / 50
    frame["body_atr"] = (frame["close"] - frame["open"]) / atr
    frame["range_atr"] = candle_range / atr
    frame["close_position"] = (frame["close"] - frame["min"]) / candle_range.replace(0, np.nan)
    for lag in (1, 2, 3):
        frame[f"return_{lag}_atr"] = frame["close"].diff(lag) / atr
    hour = timestamp.dt.hour + timestamp.dt.minute / 60
    frame["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    frame["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    frame["target"] = (frame["close"].shift(-1) > frame["open"].shift(-1)).astype(float)
    frame["decisive"] = frame["close"].shift(-1) != frame["open"].shift(-1)
    frame["contiguous"] = frame["from"].shift(-1) - frame["from"] == timeframe_seconds
    frame["relative_position"] = np.arange(len(frame)) / len(frame)
    return frame.dropna(subset=[*FEATURES])


def build_dataset(paths: list[Path], timeframe_seconds: int) -> Dataset:
    partitions: dict[str, list[np.ndarray]] = {
        "x_train": [], "y_train": [], "x_validation": [], "y_validation": [],
        "x_test": [], "y_test": [],
    }
    for path in paths:
        frame = _features(path, timeframe_seconds)
        usable = frame[frame["decisive"] & frame["contiguous"]]
        for name, low, high in (
            ("train", 0.0, 0.60), ("validation", 0.60, 0.80), ("test", 0.80, 1.01),
        ):
            part = usable[usable["relative_position"].between(low, high, inclusive="left")]
            partitions[f"x_{name}"].append(part[list(FEATURES)].to_numpy(dtype=float))
            partitions[f"y_{name}"].append(part["target"].to_numpy(dtype=float))
    return Dataset(**{key: np.concatenate(value) for key, value in partitions.items()})


@dataclass(frozen=True)
class Standardizer:
    mean: np.ndarray
    scale: np.ndarray

    def transform(self, values: np.ndarray) -> np.ndarray:
        normalized = (values - self.mean) / self.scale
        return np.column_stack([np.ones(len(normalized)), normalized])


def fit_standardizer(values: np.ndarray) -> Standardizer:
    scale = values.std(axis=0)
    return Standardizer(values.mean(axis=0), np.where(scale > 1e-12, scale, 1.0))


def fit_logistic(x: np.ndarray, y: np.ndarray, l2: float, iterations: int = 40) -> np.ndarray:
    weights = np.zeros(x.shape[1])
    penalty_matrix = np.eye(x.shape[1]) * l2
    penalty_matrix[0, 0] = 0.0
    for _ in range(iterations):
        logits = np.clip(x @ weights, -30, 30)
        probability = 1 / (1 + np.exp(-logits))
        penalty = np.r_[0.0, weights[1:]] * l2
        gradient = x.T @ (probability - y) / len(y) + penalty
        curvature = probability * (1 - probability)
        hessian = x.T @ (x * curvature[:, None]) / len(y) + penalty_matrix
        step = np.linalg.solve(hessian + np.eye(x.shape[1]) * 1e-9, gradient)
        weights -= step
        if np.linalg.norm(step) < 1e-8:
            break
    return weights


def probabilities(x: np.ndarray, weights: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.clip(x @ weights, -30, 30)))


def trade_pnls(
    probability: np.ndarray,
    target: np.ndarray,
    threshold: float,
    payout: float,
) -> list[float]:
    calls = probability >= threshold
    puts = probability <= 1 - threshold
    correct = (calls & (target == 1)) | (puts & (target == 0))
    selected = calls | puts
    return np.where(correct[selected], payout, -1.0).tolist()


def eligible(train: PerformanceReport, validation: PerformanceReport) -> bool:
    return (
        train.trades >= 500
        and validation.trades >= 200
        and train.expectancy > 0
        and validation.expectancy > 0
        and validation.wilson_low > validation.break_even_win_rate
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Modelo regularizado con test final sellado.")
    parser.add_argument("files", nargs="+")
    parser.add_argument("--timeframe-seconds", type=int, required=True)
    parser.add_argument("--payout", type=float, required=True)
    parser.add_argument("--reveal-test", action="store_true")
    args = parser.parse_args()
    dataset = build_dataset([Path(item) for item in args.files], args.timeframe_seconds)
    standardizer = fit_standardizer(dataset.x_train)
    x_train = standardizer.transform(dataset.x_train)
    x_validation = standardizer.transform(dataset.x_validation)
    x_test = standardizer.transform(dataset.x_test)

    rankings = []
    for l2 in (0.0001, 0.001, 0.01, 0.1):
        weights = fit_logistic(x_train, dataset.y_train, l2)
        train_probability = probabilities(x_train, weights)
        validation_probability = probabilities(x_validation, weights)
        for threshold in (0.52, 0.54, 0.56, 0.58, 0.60):
            train = analyze_pnls(
                trade_pnls(train_probability, dataset.y_train, threshold, args.payout),
                minimum_trades=500, minimum_edge=0,
            )
            validation = analyze_pnls(
                trade_pnls(validation_probability, dataset.y_validation, threshold, args.payout),
                minimum_trades=200, minimum_edge=0,
            )
            allowed = eligible(train, validation)
            score = validation.expectancy * np.sqrt(max(1, validation.trades))
            rankings.append((allowed, score, l2, threshold, weights, train, validation))
    rankings.sort(key=lambda row: (row[0], row[1]), reverse=True)

    print("Selección: 0-60% entrenamiento, 60-80% validación; 80-100% sellado.\n")
    for allowed, score, l2, threshold, _, train, validation in rankings[:10]:
        print(
            f"l2={l2:g} umbral={threshold:.2f} elegible={allowed} score={score:.3f} | "
            f"train n={train.trades} exp={train.expectancy:.4f} WR={train.win_rate:.2%} | "
            f"valid n={validation.trades} exp={validation.expectancy:.4f} "
            f"WR={validation.win_rate:.2%} Wilson95={validation.wilson_low:.2%}"
        )

    selected = next((row for row in rankings if row[0]), None)
    if not args.reveal_test:
        print("\nTEST FINAL NO REVELADO.")
        return
    if selected is None:
        print("\nTEST FINAL NO REVELADO: ningún modelo cumplió los criterios previos.")
        return
    _, _, l2, threshold, weights, _, _ = selected
    test = analyze_pnls(
        trade_pnls(probabilities(x_test, weights), dataset.y_test, threshold, args.payout),
        minimum_trades=200, minimum_edge=0.02,
    )
    print(
        f"\nTEST FINAL l2={l2:g} umbral={threshold:.2f}: n={test.trades} "
        f"PnL={test.pnl:.2f} exp={test.expectancy:.4f} WR={test.win_rate:.2%} "
        f"Wilson95={test.wilson_low:.2%} validada={test.validated}"
    )
    print("Coeficientes:")
    for name, coefficient in zip(("intercept", *FEATURES), weights):
        print(f"  {name}: {coefficient:.6f}")


if __name__ == "__main__":
    main()
