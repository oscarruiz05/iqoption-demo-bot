from typing import Optional
import pandas as pd
from signals import Signal


def add_indicators(candles: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(candles).sort_values("from").reset_index(drop=True)
    close = df["close"].astype(float)
    high = df["max"].astype(float)
    low = df["min"].astype(float)

    df["ema20"] = close.ewm(span=20, adjust=False).mean()
    df["ema50"] = close.ewm(span=50, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = gain / loss.replace(0, float("nan"))
    df["rsi14"] = (100 - 100 / (1 + rs)).fillna(100)

    previous_close = close.shift(1)
    true_range = pd.concat([
        high - low,
        (high - previous_close).abs(),
        (low - previous_close).abs(),
    ], axis=1).max(axis=1)
    df["atr14"] = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    smoothed_plus = plus_dm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    smoothed_minus = minus_dm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    df["plus_di14"] = 100 * smoothed_plus / df["atr14"]
    df["minus_di14"] = 100 * smoothed_minus / df["atr14"]
    di_sum = (df["plus_di14"] + df["minus_di14"]).replace(0, float("nan"))
    dx = 100 * (df["plus_di14"] - df["minus_di14"]).abs() / di_sum
    df["adx14"] = dx.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    return df


def get_signal(candles: list[dict], strategy_name: str = "trend") -> Optional[Signal]:
    """Uses only closed candles. The caller must omit the currently forming candle."""
    if len(candles) < 60:
        return None
    df = add_indicators(candles)
    if strategy_name == "support_channel":
        from support_channel import detect_support_channel_signal
        return detect_support_channel_signal(df)
    return detect_signal(df)


def detect_signal(df: pd.DataFrame) -> Optional[Signal]:
    """Apply trend-strength, pullback and confirmation filters."""
    if len(df) < 21:
        return None

    prev, last = df.iloc[-2], df.iloc[-1]
    trend_reference = df.iloc[-6]
    body = abs(last["close"] - last["open"])
    full_range = max(last["max"] - last["min"], 1e-12)
    body_ratio = body / full_range
    close_position = (last["close"] - last["min"]) / full_range
    median_range = (df["max"] - df["min"]).iloc[-21:-1].median()
    atr = float(last.get("atr14", median_range))
    if pd.isna(atr) or atr <= 0:
        return None

    adx = float(last.get("adx14", 100.0))
    if "plus_di14" in df.columns and "minus_di14" in df.columns:\n        plus_di = float(last["plus_di14"])\n        minus_di = float(last["minus_di14"])\n    else:\n        plus_di = 100.0 if last["ema20"] > last["ema50"] else 0.0\n        minus_di = 100.0 if last["ema20"] < last["ema50"] else 0.0
    ema_distance = abs(last["ema20"] - last["ema50"])
    ema20_slope = abs(last["ema20"] - trend_reference["ema20"])

    clear_body = body_ratio >= 0.60
    normal_range = median_range > 0 and 0.55 * median_range <= full_range <= 1.60 * median_range
    strong_trend = (
        not pd.isna(adx)
        and adx >= 22
        and ema_distance >= 0.35 * atr
        and ema20_slope >= 0.20 * atr
    )

    bullish_trend = (
        last["ema20"] > last["ema50"]
        and last["ema20"] > trend_reference["ema20"]
        and last["ema50"] > trend_reference["ema50"]
        and plus_di > minus_di
    )
    bearish_trend = (
        last["ema20"] < last["ema50"]
        and last["ema20"] < trend_reference["ema20"]
        and last["ema50"] < trend_reference["ema50"]
        and minus_di > plus_di
    )

    touch_tolerance = 0.15 * atr
    bullish_pullback = (
        prev["close"] < prev["open"]
        and prev["min"] <= prev["ema20"] + touch_tolerance
        and prev["max"] >= prev["ema20"] - touch_tolerance
    )
    bearish_pullback = (
        prev["close"] > prev["open"]
        and prev["max"] >= prev["ema20"] - touch_tolerance
        and prev["min"] <= prev["ema20"] + touch_tolerance
    )
    bullish_confirmation = (
        last["close"] > last["open"]
        and last["close"] > prev["open"]
        and last["close"] > last["ema20"]
        and close_position >= 0.80
        and last["close"] - last["ema20"] <= 0.80 * atr
    )
    bearish_confirmation = (
        last["close"] < last["open"]
        and last["close"] < prev["open"]
        and last["close"] < last["ema20"]
        and close_position <= 0.20
        and last["ema20"] - last["close"] <= 0.80 * atr
    )
    bullish_rsi = 52 <= last["rsi14"] <= 60 and last["rsi14"] > prev["rsi14"]
    bearish_rsi = 40 <= last["rsi14"] <= 48 and last["rsi14"] < prev["rsi14"]

    common_filters = clear_body and normal_range and strong_trend
    if common_filters and bullish_trend and bullish_pullback and bullish_confirmation and bullish_rsi:
        direction = "call"
    elif common_filters and bearish_trend and bearish_pullback and bearish_confirmation and bearish_rsi:
        direction = "put"
    else:
        return None

    return Signal(
        direction,
        int(last["from"]),
        float(last["close"]),
        float(last["ema20"]),
        float(last["ema50"]),
        float(last["rsi14"]),
        f"ADX={adx:.1f} + EMA/ATR + retroceso contrario + confirmacion fuerte",
    )
