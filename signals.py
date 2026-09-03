from dataclasses import dataclass


@dataclass(frozen=True)
class Signal:
    direction: str
    candle_time: int
    close: float
    ema20: float
    ema50: float
    rsi14: float
    reason: str
    strategy: str = "trend"
