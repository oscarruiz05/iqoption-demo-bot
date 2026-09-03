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
    prev, last = df.iloc[-2], df.iloc[-1]
    body = abs(last["close"] - last["open"])
    full_range = max(last["max"] - last["min"], 1e-12)
    clear_body = body / full_range >= 0.45

    bullish_trend = last["ema20"] > last["ema50"] and last["ema20"] > prev["ema20"]
    bearish_trend = last["ema20"] < last["ema50"] and last["ema20"] < prev["ema20"]
    bullish_confirmation = last["close"] > last["open"] and last["close"] > prev["close"]
    bearish_confirmation = last["close"] < last["open"] and last["close"] < prev["close"]
    near_ema20 = abs(last["close"] - last["ema20"]) / last["close"] <= 0.0035

    if bullish_trend and near_ema20 and clear_body and bullish_confirmation and 45 <= last["rsi14"] <= 65:
        direction = "call"
    elif bearish_trend and near_ema20 and clear_body and bearish_confirmation and 35 <= last["rsi14"] <= 55:
        direction = "put"
    else:
        return None

    return Signal(direction, int(last["from"]), float(last["close"]),
                  float(last["ema20"]), float(last["ema50"]), float(last["rsi14"]),
                  "tendencia + retroceso EMA20 + confirmacion + RSI")
