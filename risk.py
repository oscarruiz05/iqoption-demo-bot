from dataclasses import dataclass
from datetime import date, datetime, timezone, tzinfo
import csv
from pathlib import Path


def extract_pnl(result) -> float:
    """Normalize iqoptionapi result formats such as (True, 0.85)."""
    if isinstance(result, (tuple, list)):
        if len(result) < 2:
            raise ValueError(f"Resultado incompleto de IQ Option: {result!r}")
        closed, pnl = result[0], result[1]
        if closed is False or pnl is None:
            raise ValueError(f"La operacion aun no tiene resultado: {result!r}")
        return float(pnl)
    if result is None:
        raise ValueError("IQ Option devolvio un resultado vacio")
    return float(result)


@dataclass
class RiskManager:
    max_trades: int
    max_consecutive_losses: int
    max_daily_loss: float
    trades: int = 0
    consecutive_losses: int = 0
    pnl: float = 0.0

    def can_trade(self, next_stake: float = 0.0) -> tuple[bool, str]:
        if self.trades >= self.max_trades:
            return False, "maximo de operaciones diarias alcanzado"
        if self.consecutive_losses >= self.max_consecutive_losses:
            return False, "maximo de perdidas consecutivas alcanzado"
        if self.pnl <= -self.max_daily_loss:
            return False, "perdida diaria maxima alcanzada"
        if next_stake > 0 and self.pnl - next_stake < -self.max_daily_loss:
            return False, "la siguiente operacion excederia la perdida diaria maxima"
        return True, "ok"

    def record(self, pnl: float) -> None:
        self.trades += 1
        self.pnl += pnl
        self.consecutive_losses = self.consecutive_losses + 1 if pnl < 0 else 0


def load_daily_risk(
    path: Path,
    max_trades: int,
    max_consecutive_losses: int,
    max_daily_loss: float,
    *,
    day: date | None = None,
    day_timezone: tzinfo = timezone.utc,
) -> RiskManager:
    """Rebuild today's limits so restarting the bot cannot reset the risk state."""
    manager = RiskManager(max_trades, max_consecutive_losses, max_daily_loss)
    if not path.exists():
        return manager
    target_day = day or datetime.now(day_timezone).date()
    with path.open("r", newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            try:
                timestamp = datetime.fromisoformat(row["utc_time"].replace("Z", "+00:00"))
                pnl = float(row["pnl"])
            except (KeyError, TypeError, ValueError):
                continue
            if timestamp.astimezone(day_timezone).date() == target_day:
                manager.record(pnl)
    return manager
