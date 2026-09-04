from dataclasses import dataclass
import os
from dotenv import load_dotenv
from assets import parse_assets

load_dotenv()

REAL_CONFIRMATION_PHRASE = "ACEPTO_RIESGO_REAL"


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "si"}


def validate_account_mode(
    account: str,
    enable_trading: bool,
    enable_real_trading: bool,
    confirmation: str,
    amount: float,
    max_real_amount: float,
) -> None:
    if account not in {"PRACTICE", "REAL"}:
        raise ValueError("IQ_ACCOUNT debe ser PRACTICE o REAL")
    if max_real_amount <= 0:
        raise ValueError("MAX_REAL_AMOUNT debe ser mayor que cero")
    if account == "REAL" and enable_trading:
        if not enable_real_trading:
            raise ValueError("Para operar en REAL configura ENABLE_REAL_TRADING=true")
        if confirmation != REAL_CONFIRMATION_PHRASE:
            raise ValueError(
                f"Para operar en REAL configura REAL_TRADING_CONFIRMATION={REAL_CONFIRMATION_PHRASE}"
            )
        if amount > max_real_amount:
            raise ValueError(
                f"IQ_AMOUNT={amount:g} supera MAX_REAL_AMOUNT={max_real_amount:g}"
            )


@dataclass(frozen=True)
class Settings:
    email: str = os.getenv("IQ_EMAIL", "")
    password: str = os.getenv("IQ_PASSWORD", "")
    account: str = os.getenv("IQ_ACCOUNT", "PRACTICE").strip().upper()
    assets: tuple[str, ...] = parse_assets(
        os.getenv("IQ_ASSETS", os.getenv("IQ_ASSET", "AUDCAD-OTC"))
    )
    amount: float = float(os.getenv("IQ_AMOUNT", "1"))
    timeframe_min: int = int(os.getenv("IQ_TIMEFRAME_MIN", "5"))
    expiration_min: int = int(os.getenv("IQ_EXPIRATION_MIN", "5"))
    strategy: str = os.getenv("IQ_STRATEGY", "trend").strip().lower()
    enable_trading: bool = _bool("ENABLE_TRADING")
    enable_real_trading: bool = _bool("ENABLE_REAL_TRADING")
    real_trading_confirmation: str = os.getenv("REAL_TRADING_CONFIRMATION", "").strip()
    max_real_amount: float = float(os.getenv("MAX_REAL_AMOUNT", "1"))
    min_candles_between_trades: int = int(os.getenv("MIN_CANDLES_BETWEEN_TRADES", "5"))
    max_trades_day: int = int(os.getenv("MAX_TRADES_DAY", "10"))
    max_consecutive_losses: int = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))
    max_daily_loss: float = float(os.getenv("MAX_DAILY_LOSS", "5"))

    def validate(self) -> None:
        if not self.email or not self.password:
            raise ValueError("Completa IQ_EMAIL e IQ_PASSWORD en el archivo .env")
        if not self.assets:
            raise ValueError("Configura al menos un par en IQ_ASSETS")
        if self.amount <= 0 or self.max_daily_loss <= 0:
            raise ValueError("Los montos deben ser mayores que cero")
        if self.timeframe_min not in {1, 5, 15}:
            raise ValueError("IQ_TIMEFRAME_MIN debe ser 1, 5 o 15")
        if self.expiration_min not in {1, 5, 15}:
            raise ValueError("IQ_EXPIRATION_MIN debe ser 1, 5 o 15")
        if self.min_candles_between_trades < 1:
            raise ValueError("MIN_CANDLES_BETWEEN_TRADES debe ser al menos 1")
        if self.strategy not in {"trend", "support_channel"}:
            raise ValueError("IQ_STRATEGY debe ser trend o support_channel")
        validate_account_mode(
            self.account,
            self.enable_trading,
            self.enable_real_trading,
            self.real_trading_confirmation,
            self.amount,
            self.max_real_amount,
        )
