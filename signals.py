from dataclasses import dataclass
from typing import Optional


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
    expiration_min: int | None = None
    metrics: Optional[dict[str, float]] = None
