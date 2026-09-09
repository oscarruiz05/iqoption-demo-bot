from typing import Optional

import pandas as pd

from signals import Signal


def add_bollinger_reversal_indicators(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    close = result["close"].astype(float)
    high = result["max"].astype(float)
    low = result["min"].astype(float)

    middle = close.rolling(6).mean()
    deviation = close.rolling(6).std(ddof=0)
    result["bb_middle6"] = middle
    result["bb_upper6"] = middle + 2 * deviation
    result["bb_lower6"] = middle - 2 * deviation
    result["ema100"] = close.ewm(span=100, adjust=False).mean()

    lowest = low.rolling(13).min()
    highest = high.rolling(13).max()
    stochastic_range = (highest - lowest).replace(0, float("nan"))
    raw_k = 100 * (close - lowest) / stochastic_range
    result["stoch_k"] = raw_k.rolling(3).mean()
    result["stoch_d"] = result["stoch_k"].rolling(3).mean()

    typical = (high + low + close) / 3
    typical_mean = typical.rolling(14).mean()
    mean_deviation = typical.rolling(14).apply(
        lambda values: float((values - values.mean()).abs().mean()), raw=False
    )
    result["cci14"] = (
        (typical - typical_mean) / (0.015 * mean_deviation.replace(0, float("nan")))
    )
    return result


def detect_bollinger_reversal_signal(df: pd.DataFrame) -> Optional[Signal]:
    """Trend-aligned Bollinger rejection with Stochastic and CCI confirmation."""
    if len(df) < 105:
        return None

    enriched = add_bollinger_reversal_indicators(df)
    prev, last = enriched.iloc[-2], enriched.iloc[-1]
    required = (
        "bb_upper6", "bb_lower6", "ema100", "stoch_k", "stoch_d", "cci14", "atr14"
    )
    if any(pd.isna(last[column]) for column in required):
        return None

    atr = float(last["atr14"])
    if atr <= 0:
        return None

    ema_reference = enriched.iloc[-6]["ema100"]
    ema_slope = float(last["ema100"] - ema_reference)
    normalized_slope = abs(ema_slope) / atr
    candle_range = float(last["max"] - last["min"])
    normal_volatility = candle_range <= 2.0 * atr
    closes_inside_lower = last["close"] > last["bb_lower6"]
    closes_inside_upper = last["close"] < last["bb_upper6"]

    bullish_trend = (
        last["close"] > last["ema100"]
        and ema_slope >= 0.05 * atr
    )
    bearish_trend = (
        last["close"] < last["ema100"]
        and ema_slope <= -0.05 * atr
    )
    oversold_turn = (
        last["stoch_k"] <= 20
        and last["stoch_d"] <= 20
        and prev["stoch_k"] <= prev["stoch_d"]
        and last["stoch_k"] > last["stoch_d"]
        and last["cci14"] <= -100
        and last["cci14"] > prev["cci14"]
    )
    overbought_turn = (
        last["stoch_k"] >= 80
        and last["stoch_d"] >= 80
        and prev["stoch_k"] >= prev["stoch_d"]
        and last["stoch_k"] < last["stoch_d"]
        and last["cci14"] >= 100
        and last["cci14"] < prev["cci14"]
    )

    call_setup = (
        normal_volatility
        and bullish_trend
        and last["min"] < last["bb_lower6"]
        and closes_inside_lower
        and oversold_turn
    )
    put_setup = (
        normal_volatility
        and bearish_trend
        and last["max"] > last["bb_upper6"]
        and closes_inside_upper
        and overbought_turn
    )
    if not call_setup and not put_setup:
        return None

    direction = "call" if call_setup else "put"
    expiration_min = 3 if normalized_slope >= 0.15 else 4
    reason = (
        f"BB(6,2) rechazo + EMA100 tendencia + Stoch(13,3,3) "
        f"+ CCI14 | expiracion={expiration_min}m"
    )
    return Signal(
        direction,
        int(last["from"]),
        float(last["close"]),
        float(last["ema20"]),
        float(last["ema50"]),
        float(last["rsi14"]),
        reason,
        "bollinger_reversal",
        expiration_min,
    )
