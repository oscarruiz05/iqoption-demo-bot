from dataclasses import dataclass


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

    def can_trade(self) -> tuple[bool, str]:
        if self.trades >= self.max_trades:
            return False, "maximo de operaciones diarias alcanzado"
        if self.consecutive_losses >= self.max_consecutive_losses:
            return False, "maximo de perdidas consecutivas alcanzado"
        if self.pnl <= -self.max_daily_loss:
            return False, "perdida diaria maxima alcanzada"
        return True, "ok"

    def record(self, pnl: float) -> None:
        self.trades += 1
        self.pnl += pnl
        self.consecutive_losses = self.consecutive_losses + 1 if pnl < 0 else 0
