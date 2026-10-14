"""Consulta de payout con caché y comportamiento fail-closed."""

from __future__ import annotations

import time


def option_kind(expiration_min: int) -> str:
    return "turbo" if expiration_min <= 5 else "binary"


class PayoutCache:
    def __init__(self, client, ttl_seconds: float = 60.0):
        self.client = client
        self.ttl_seconds = ttl_seconds
        self._updated_at = 0.0
        self._profits = {}

    def _refresh_if_older_than(self, max_age: float) -> None:
        now = time.monotonic()
        if not self._profits or now - self._updated_at >= max_age:
            self._profits = self.client.get_all_profit() or {}
            self._updated_at = now

    def prefetch(self, margin_seconds: float = 15.0) -> None:
        """Renueva en tiempo muerto para que get() no consulte la API tras una señal."""
        self._refresh_if_older_than(max(0.0, self.ttl_seconds - margin_seconds))

    def get(self, asset: str, expiration_min: int) -> float | None:
        self._refresh_if_older_than(self.ttl_seconds)
        raw = self._profits.get(asset, {}).get(option_kind(expiration_min))
        if raw is None:
            return None
        value = float(raw)
        if value > 1:
            value /= 100
        return value if 0 < value <= 1 else None
