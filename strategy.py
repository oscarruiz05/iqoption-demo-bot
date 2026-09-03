from dataclasses import dataclass
from typing import Optional
import pandas as pd


@dataclass(frozen=True)
class Signal:
    direction: str
    candle_time: int
    close: float
    ema20: float
    ema50: float
    rsi14: float
    reason: str


def add_indicators(candles: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(candles).sort_values("from").reset_index(drop=True)
    close = df["close"].astype(float)
    df["ema20"] = close.ewm(span=20, adjust=False).mean()
    df["ema50"] = close.ewm(span=50, adjust=False).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = gain / loss.replace(0, float("nan"))
    df["rsi14"] = (100 - 100 / (1 + rs)).fillna(100)
    return df


def get_signal(candles: list[dict]) -> Optional[Signal]:
    """Uses only closed candles. The caller must omit the currently forming candle."""
    if len(candles) < 60:
        return None
    df = add_indicators(candles)
    return detect_signal(df)


def detect_signal(df: pd.DataFrame) -> Optional[Signal]:
    """Apply strict entry filters to a dataframe that already has indicators."""
    if len(df) < 21:
        return None

    prev, last = df.iloc[-2], df.iloc[-1]
    trend_reference = df.iloc[-4]
    body = abs(last["close"] - last["open"])
    full_range = max(last["max"] - last["min"], 1e-12)
    body_ratio = body / full_range
    close_position = (last["close"] - last["min"]) / full_range
    median_range = (df["max"] - df["min"]).iloc[-21:-1].median()

    clear_body = body_ratio >= 0.55
    normal_range = median_range > 0 and full_range <= median_range * 1.8
    ema_separation = abs(last["ema20"] - last["ema50"]) / last["close"] >= 0.00025

    bullish_trend = (
        last["ema20"] > last["ema50"]
        and last["ema20"] > trend_reference["ema20"]
        and last["ema50"] > trend_reference["ema50"]
    )
    bearish_trend = (
        last["ema20"] < last["ema50"]
        and last["ema20"] < trend_reference["ema20"]
        and last["ema50"] < trend_reference["ema50"]
    )

    bullish_pullback = prev["min"] <= prev["ema20"] * 1.0005 and last["close"] > last["ema20"]
    bearish_pullback = prev["max"] >= prev["ema20"] * 0.9995 and last["close"] < last["ema20"]
    bullish_confirmation = (
        last["close"] > last["open"]
        and last["close"] > prev["close"]
        and close_position >= 0.75
    )
    bearish_confirmation = (
        last["close"] < last["open"]
        and last["close"] < prev["close"]
        and close_position <= 0.25
    )
    bullish_rsi = 48 <= last["rsi14"] <= 62 and last["rsi14"] > prev["rsi14"]
    bearish_rsi = 38 <= last["rsi14"] <= 52 and last["rsi14"] < prev["rsi14"]

    common_filters = clear_body and normal_range and ema_separation
    if common_filters and bullish_trend and bullish_pullback and bullish_confirmation and bullish_rsi:
        direction = "call"
    elif common_filters and bearish_trend and bearish_pullback and bearish_confirmation and bearish_rsi:
        direction = "put"
    else:
        return None

    return Signal(direction, int(last["from"]), float(last["close"]),
                  float(last["ema20"]), float(last["ema50"]), float(last["rsi14"]),
                  "EMA20/50 con pendiente + retroceso real + vela fuerte + RSI con impulso")
