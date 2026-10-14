"""Seguimiento no bloqueante de órdenes y caché incremental de velas."""

from __future__ import annotations

from dataclasses import dataclass

from signals import Signal


# Tras el vencimiento, si el WebSocket no notificó el cierre (p. ej. por una
# reconexión que creó un cliente nuevo), se consulta el historial de opciones.
RESULT_FALLBACK_SECONDS = 90
RESULT_FALLBACK_INTERVAL_SECONDS = 60


@dataclass
class PendingOrder:
    order_id: int
    asset: str
    signal: Signal
    amount: float
    expiration_min: int
    expires_at: float
    quoted_payout: float | None = None
    signal_delay_seconds: float | None = None
    order_delay_seconds: float | None = None
    # Apertura de la vela de entrada: el precio que supone el backtest.
    reference_open: float | None = None
    fallback_checked_at: float = 0.0


def closed_option_pnl(message) -> float | None:
    """PnL de un mensaje socket-option-closed, con el cálculo de check_win_v4."""
    msg = message.get("msg") if isinstance(message, dict) else None
    if not isinstance(msg, dict) or "win" not in msg:
        return None
    if msg["win"] == "equal":
        return 0.0
    if msg["win"] == "loose":
        return -float(msg["sum"])
    return float(msg["win_amount"]) - float(msg["sum"])


def poll_order_pnl(client, order_id) -> float | None:
    """Devuelve el PnL si IQ Option ya notificó el cierre; nunca espera."""
    closed = getattr(client.api, "socket_option_closed", None) or {}
    message = closed.get(order_id)
    return None if message is None else closed_option_pnl(message)


def find_closed_option_pnl(client, order_id, limit: int = 30) -> float | None:
    """Respaldo: busca la orden entre las últimas opciones cerradas de la cuenta."""
    data = client.get_optioninfo_v2(limit) or {}
    options = (data.get("msg") or {}).get("closed_options") or []
    for option in options:
        ids = option.get("id")
        ids = ids if isinstance(ids, (list, tuple)) else [ids]
        if order_id not in ids:
            continue
        if option.get("win") == "equal":
            return 0.0
        return float(option.get("win_amount") or 0) - float(option["amount"])
    return None


def order_entry_price(client, order_id) -> float | None:
    """Cotización de apertura informada por IQ Option, si el mensaje la incluye."""
    for store in ("socket_option_opened", "socket_option_closed"):
        message = (getattr(client.api, store, None) or {}).get(order_id)
        msg = message.get("msg") if isinstance(message, dict) else None
        if isinstance(msg, dict) and msg.get("value") not in (None, ""):
            try:
                return float(msg["value"])
            except (TypeError, ValueError):
                return None
    return None


def entry_slippage_atr(
    direction: str,
    entry_price: float | None,
    reference_open: float | None,
    atr: float | None,
) -> float | None:
    """Diferencia entre la entrada real y la del backtest. Positivo = peor entrada."""
    if entry_price is None or reference_open is None or not atr or atr <= 0:
        return None
    if reference_open <= 0 or abs(entry_price / reference_open - 1) > 0.05:
        # Escala distinta o dato erróneo: mejor no registrar una cifra engañosa.
        return None
    sign = 1 if direction == "call" else -1
    return sign * (entry_price - reference_open) / atr


class CandleCache:
    """Conserva la historia de cada par y solo descarga las últimas velas por ciclo."""

    def __init__(self, size: int, refresh_count: int = 5):
        self.size = size
        self.refresh_count = min(refresh_count, size)
        self._candles: dict[str, list[dict]] = {}

    def request_count(self, asset: str, now: float, timeframe_seconds: int) -> int:
        cached = self._candles.get(asset)
        if not cached or len(cached) < self.size:
            return self.size
        newest = int(cached[-1]["from"])
        # Si la descarga corta no alcanzaría a solaparse con la caché, quedaría un hueco.
        if now - newest > (self.refresh_count - 1) * timeframe_seconds:
            return self.size
        return self.refresh_count

    def merge(self, asset: str, candles: list[dict]) -> list[dict]:
        by_time = {int(c["from"]): c for c in self._candles.get(asset, [])}
        # Las velas nuevas reemplazan a las cacheadas: la vela en formación cambia.
        by_time.update({int(c["from"]): c for c in candles})
        merged = [by_time[key] for key in sorted(by_time)][-self.size:]
        self._candles[asset] = merged
        return merged
