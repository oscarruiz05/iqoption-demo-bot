from typing import Optional

import pandas as pd

from signals import Signal


def add_freedom_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add the exact indicators used by the Freedom setup."""
    result = df.copy()
    close = result["close"].astype(float)

    result["ema200"] = close.ewm(span=200, adjust=False).mean()

    middle = close.rolling(14).mean()
    deviation = close.rolling(14).std(ddof=0)
    result["bb_middle14"] = middle
    result["bb_upper14"] = middle + 2 * deviation
    result["bb_lower14"] = middle - 2 * deviation

    delta = close.diff()
    gain = delta.clip(lower=0).ewm(
        alpha=1 / 10, adjust=False, min_periods=10
    ).mean()
    loss = (-delta.clip(upper=0)).ewm(
        alpha=1 / 10, adjust=False, min_periods=10
    ).mean()
    rs = gain / loss.replace(0, float("nan"))
    rsi = 100 - 100 / (1 + rs)
    result["rsi10"] = rsi.where(loss.ne(0), 100.0)
    result.loc[gain.eq(0) & loss.gt(0), "rsi10"] = 0.0
    return result


def detect_freedom_signal(df: pd.DataFrame) -> Optional[Signal]:
    """Freedom: EMA200 trend + Bollinger close breakout + RSI10 extreme."""
    if len(df) < 205:
        return None

    enriched = add_freedom_indicators(df)
    last = enriched.iloc[-1]
    ema_reference = enriched.iloc[-6]
    recent = enriched.iloc[-5:]

    required = ("ema200", "bb_upper14", "bb_lower14", "rsi10", "atr14")
    if any(pd.isna(last[column]) for column in required):
        return None

    atr = float(last["atr14"])
    if atr <= 0:
        return None

    ema_slope = float(last["ema200"] - ema_reference["ema200"])
    closes_above_ema = int((recent["close"] > recent["ema200"]).sum())
    closes_below_ema = int((recent["close"] < recent["ema200"]).sum())
    bullish_trend = (
        last["close"] > last["ema200"]
        and ema_slope >= 0.15 * atr
        and closes_above_ema >= 4
    )
    bearish_trend = (
        last["close"] < last["ema200"]
        and ema_slope <= -0.15 * atr
        and closes_below_ema >= 4
    )

    lower_break_atr = float(last["bb_lower14"] - last["close"]) / atr
    upper_break_atr = float(last["close"] - last["bb_upper14"]) / atr
    call_setup = (
        bullish_trend
        and lower_break_atr >= 0.25 - 1e-12
        and last["rsi10"] <= 30
    )
    put_setup = (
        bearish_trend
        and upper_break_atr >= 0.25 - 1e-12
        and last["rsi10"] >= 70
    )
    if not call_setup and not put_setup:
        return None

    direction = "call" if call_setup else "put"
    reason = (
        f"Freedom | EMA200 tendencia + cierre fuera BB(14,2) "
        f"+ RSI10={float(last['rsi10']):.2f}"
    )
    return Signal(
        direction,
        int(last["from"]),
        float(last["close"]),
        float(last["ema200"]),
        float(last["ema200"]),
        float(last["rsi10"]),
        reason,
        "freedom",
        5,
        {
            "ema200": float(last["ema200"]),
            "ema200_slope": ema_slope,
            "ema_slope_atr": ema_slope / atr,
            "bb_upper": float(last["bb_upper14"]),
            "bb_lower": float(last["bb_lower14"]),
            "rsi10": float(last["rsi10"]),
            "band_break_atr": lower_break_atr if direction == "call" else upper_break_atr,
            "trend_side_count": float(
                closes_above_ema if direction == "call" else closes_below_ema
            ),
        },
    )
