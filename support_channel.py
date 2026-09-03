from typing import Optional
import numpy as np
import pandas as pd

from signals import Signal


def cluster_levels(levels: list[float], tolerance: float, minimum_touches: int = 2) -> list[float]:
    if not levels or tolerance <= 0:
        return []
    clusters: list[list[float]] = []
    for level in sorted(levels):
        if not clusters or abs(level - sum(clusters[-1]) / len(clusters[-1])) > tolerance:
            clusters.append([level])
        else:
            clusters[-1].append(level)
    return [sum(cluster) / len(cluster) for cluster in clusters if len(cluster) >= minimum_touches]


def bullish_rejection(row) -> bool:
    body = abs(row["close"] - row["open"])
    candle_range = max(row["max"] - row["min"], 1e-12)
    lower_wick = min(row["open"], row["close"]) - row["min"]
    close_position = (row["close"] - row["min"]) / candle_range
    return row["close"] > row["open"] and lower_wick >= max(body * 1.2, candle_range * 0.25) and close_position >= 0.65


def bearish_rejection(row) -> bool:
    body = abs(row["close"] - row["open"])
    candle_range = max(row["max"] - row["min"], 1e-12)
    upper_wick = row["max"] - max(row["open"], row["close"])
    close_position = (row["close"] - row["min"]) / candle_range
    return row["close"] < row["open"] and upper_wick >= max(body * 1.2, candle_range * 0.25) and close_position <= 0.35


def _pivot_levels(df: pd.DataFrame) -> tuple[list[float], list[float]]:
    lows, highs = [], []
    for index in range(2, len(df) - 2):
        window = df.iloc[index - 2:index + 3]
        row = df.iloc[index]
        if row["min"] <= window["min"].min():
            lows.append(float(row["min"]))
        if row["max"] >= window["max"].max():
            highs.append(float(row["max"]))
    return lows, highs


def detect_support_channel_signal(df: pd.DataFrame) -> Optional[Signal]:
    if len(df) < 60 or pd.isna(df.iloc[-1].get("atr14")):
        return None

    prev, last = df.iloc[-2], df.iloc[-1]
    atr = float(last["atr14"])
    if atr <= 0:
        return None
    tolerance = atr * 0.35

    historical = df.iloc[:-2]
    pivot_lows, pivot_highs = _pivot_levels(historical)
    supports = cluster_levels(pivot_lows, tolerance)
    resistances = cluster_levels(pivot_highs, tolerance)

    support_candidates = [level for level in supports if level <= last["close"] + tolerance]
    resistance_candidates = [level for level in resistances if level >= last["close"] - tolerance]
    support = max(support_candidates) if support_candidates else None
    resistance = min(resistance_candidates) if resistance_candidates else None

    channel_history = df.iloc[-41:-1]
    x = np.arange(len(channel_history), dtype=float)
    slope, intercept = np.polyfit(x, channel_history["close"].astype(float), 1)
    center = slope * len(channel_history) + intercept
    residuals = channel_history["close"].astype(float) - (slope * x + intercept)
    width = max(float(residuals.std()) * 2.0, atr * 1.5)
    lower_channel, upper_channel = center - width, center + width
    channel_is_stable = abs(slope * len(channel_history) / last["close"]) <= 0.01

    recent_median_range = float((df["max"] - df["min"]).iloc[-21:-1].median())
    normal_range = recent_median_range > 0 and (last["max"] - last["min"]) <= recent_median_range * 1.8
    call_rsi = 30 <= last["rsi14"] <= 50 and last["rsi14"] > prev["rsi14"]
    put_rsi = 50 <= last["rsi14"] <= 70 and last["rsi14"] < prev["rsi14"]

    call_setup = (
        support is not None
        and last["min"] <= support + tolerance
        and last["close"] > support
        and last["min"] <= lower_channel + tolerance
        and bullish_rejection(last)
        and call_rsi
    )
    put_setup = (
        resistance is not None
        and last["max"] >= resistance - tolerance
        and last["close"] < resistance
        and last["max"] >= upper_channel - tolerance
        and bearish_rejection(last)
        and put_rsi
    )

    if not channel_is_stable or not normal_range:
        return None
    if call_setup:
        direction = "call"
        reason = f"rebote soporte {support:.5f} + canal inferior + rechazo + RSI"
    elif put_setup:
        direction = "put"
        reason = f"rechazo resistencia {resistance:.5f} + canal superior + RSI"
    else:
        return None

    return Signal(direction, int(last["from"]), float(last["close"]),
                  float(last["ema20"]), float(last["ema50"]), float(last["rsi14"]),
                  reason, "support_channel")
