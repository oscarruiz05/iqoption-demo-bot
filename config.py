from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "si"}


@dataclass(frozen=True)
class Settings:
    email: str = os.getenv("IQ_EMAIL", "")
    password: str = os.getenv("IQ_PASSWORD", "")
    asset: str = os.getenv("IQ_ASSET", "AUDCAD-OTC").upper()
    amount: float = float(os.getenv("IQ_AMOUNT", "1"))
    timeframe_min: int = int(os.getenv("IQ_TIMEFRAME_MIN", "5"))
    expiration_min: int = int(os.getenv("IQ_EXPIRATION_MIN", "5"))
    enable_trading: bool = _bool("ENABLE_TRADING")
    max_trades_day: int = int(os.getenv("MAX_TRADES_DAY", "10"))
    max_consecutive_losses: int = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))
    max_daily_loss: float = float(os.getenv("MAX_DAILY_LOSS", "5"))

    def validate(self) -> None:
        if not self.email or not self.password:
            raise ValueError("Completa IQ_EMAIL e IQ_PASSWORD en el archivo .env")
        if self.amount <= 0 or self.max_daily_loss <= 0:
            raise ValueError("Los montos deben ser mayores que cero")
        if self.timeframe_min not in {1, 5, 15}:
            raise ValueError("IQ_TIMEFRAME_MIN debe ser 1, 5 o 15")
        if self.expiration_min not in {1, 5, 15}:
            raise ValueError("IQ_EXPIRATION_MIN debe ser 1, 5 o 15")
