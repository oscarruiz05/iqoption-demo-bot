from typing import Optional

import pandas as pd

from freedom import add_freedom_indicators
from signals import Signal


def detect_freedom_v3_signal(df: pd.DataFrame) -> Optional[Signal]:
    """Freedom v3: extremo confirmado por reingreso, sin caminar por la banda."""
    if len(df) < 206:
        return None

    enriched = add_freedom_indicators(df)
    confirmation = enriched.iloc[-1]
    setup = enriched.iloc[-2]
    ema_reference = enriched.iloc[-7]
    trend_window = enriched.iloc[-6:-1]
    band_walk_window = enriched.iloc[-4:-1]

    required = ("ema200", "bb_upper14", "bb_lower14", "rsi10", "atr14")
    if any(pd.isna(setup[column]) for column in required):
        return None
    if any(pd.isna(confirmation[column]) for column in required[:-1]):
        return None

    atr = float(setup["atr14"])
    if atr <= 0:
        return None

    ema_slope = float(setup["ema200"] - ema_reference["ema200"])
    closes_above_ema = int(
        (trend_window["close"] > trend_window["ema200"]).sum()
    )
    closes_below_ema = int(
        (trend_window["close"] < trend_window["ema200"]).sum()
    )
    bullish_trend = (
        setup["close"] > setup["ema200"]
        and ema_slope >= 0.15 * atr
        and closes_above_ema >= 4
    )
    bearish_trend = (
        setup["close"] < setup["ema200"]
        and ema_slope <= -0.15 * atr
        and closes_below_ema >= 4
    )

    lower_break_atr = float(setup["bb_lower14"] - setup["close"]) / atr
    upper_break_atr = float(setup["close"] - setup["bb_upper14"]) / atr
    lower_band_walk = int(
        (band_walk_window["close"] < band_walk_window["bb_lower14"]).sum()
    )
    upper_band_walk = int(
        (band_walk_window["close"] > band_walk_window["bb_upper14"]).sum()
    )

    call_setup = (
        bullish_trend
        and lower_break_atr >= 0.25 - 1e-12
        and setup["rsi10"] <= 30
        and lower_band_walk <= 1
    )
    put_setup = (
        bearish_trend
        and upper_break_atr >= 0.25 - 1e-12
        and setup["rsi10"] >= 70
        and upper_band_walk <= 1
    )
    call_confirmation = (
        confirmation["close"] > confirmation["open"]
        and confirmation["close"] > confirmation["bb_lower14"]
        and confirmation["rsi10"] > setup["rsi10"]
    )
    put_confirmation = (
        confirmation["close"] < confirmation["open"]
        and confirmation["close"] < confirmation["bb_upper14"]
        and confirmation["rsi10"] < setup["rsi10"]
    )

    if call_setup and call_confirmation:
        direction = "call"
        break_atr = lower_break_atr
        trend_side_count = closes_above_ema
        band_walk_count = lower_band_walk
    elif put_setup and put_confirmation:
        direction = "put"
        break_atr = upper_break_atr
        trend_side_count = closes_below_ema
        band_walk_count = upper_band_walk
    else:
        return None

    reason = (
        "Freedom v3 | extremo BB confirmado por reingreso "
        f"+ RSI10 {float(setup['rsi10']):.2f}->{float(confirmation['rsi10']):.2f} "
        "+ sin band walk"
    )
    return Signal(
        direction,
        int(confirmation["from"]),
        float(confirmation["close"]),
        float(setup["ema200"]),
        float(setup["ema200"]),
        float(confirmation["rsi10"]),
        reason,
        "freedom_v3",
        5,
        {
            "ema200": float(setup["ema200"]),
            "ema200_slope": ema_slope,
            "ema_slope_atr": ema_slope / atr,
            "bb_upper": float(setup["bb_upper14"]),
            "bb_lower": float(setup["bb_lower14"]),
            "rsi10": float(confirmation["rsi10"]),
            "setup_rsi10": float(setup["rsi10"]),
            "band_break_atr": break_atr,
            "trend_side_count": float(trend_side_count),
            "band_walk_count": float(band_walk_count),
        },
    )
