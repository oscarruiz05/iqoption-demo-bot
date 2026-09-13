"""Run the Freedom strategy against IQ Option's official MCP service.

Safe defaults: TRAINING balance, signal-only mode, one scan.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from datetime import datetime
from typing import Any

from dotenv import load_dotenv

from mcp_provider import IQOptionMCPProvider, MCPConfigurationError
from strategy import get_signal

LOGGER = logging.getLogger("mcp-freedom")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def extract_rows(payload: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        for key in ("result", "data"):
            nested = payload.get(key)
            if nested is not None:
                rows = extract_rows(nested, *keys)
                if rows:
                    return rows
    return []


def parse_expiration(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
        try:
            return int(datetime.fromisoformat(stripped.replace("Z", "+00:00")).timestamp())
        except ValueError:
            return None
    if isinstance(value, dict):
        for key in ("expired", "expiration", "timestamp", "time"):
            if key in value:
                return parse_expiration(value[key])
    return None


def choose_expiration(
    offered: list[Any], target_minutes: int, now: int | None = None
) -> int | None:
    current = int(time.time()) if now is None else now
    target = current + target_minutes * 60
    valid = sorted(
        expiration
        for expiration in (parse_expiration(item) for item in offered)
        if expiration is not None and expiration > current
    )
    if not valid:
        return None
    return min(valid, key=lambda expiration: abs(expiration - target))


def normalize_candles(payload: Any, now: int) -> list[dict[str, Any]]:
    rows = extract_rows(payload, "candles")
    normalized = []
    for row in rows:
        candle = dict(row)
        if "from" not in candle and "start" in candle:
            candle["from"] = parse_expiration(candle["start"])
        if "max" not in candle and "high" in candle:
            candle["max"] = candle["high"]
        if "min" not in candle and "low" in candle:
            candle["min"] = candle["low"]
        required = {"from", "open", "close", "min", "max"}
        if not required.issubset(candle) or candle["from"] is None:
            continue
        # Freedom must only receive fully closed one-minute candles.
        if int(candle["from"]) + 60 <= now:
            normalized.append(candle)
    return sorted(normalized, key=lambda row: int(row["from"]))


def select_balance(rows: list[dict[str, Any]], account: str) -> dict[str, Any]:
    expected = "training" if account == "TRAINING" else "regular"
    matches = [row for row in rows if str(row.get("type", "")).lower() == expected]
    if not matches:
        raise MCPConfigurationError(f"No se encontró saldo {expected}")
    return matches[0]


def canonical_asset_name(value: Any) -> str:
    """Match EURUSD-OTC, EUR/USD (OTC), and similar display formats."""
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def select_assets(
    rows: list[dict[str, Any]], requested_names: set[str]
) -> list[dict[str, Any]]:
    requested = {canonical_asset_name(name) for name in requested_names}
    return [
        row
        for row in rows
        if bool(row.get("is_open", True))
        and canonical_asset_name(row.get("name", "")) in requested
    ]


async def scan_once(
    provider: IQOptionMCPProvider,
    *,
    account: str,
    amount: float,
    requested_names: set[str],
    last_signals: dict[int, int],
) -> int:
    balance_rows = extract_rows(
        await provider.list_balances(account), "balances"
    )
    balance = select_balance(balance_rows, account)
    available_assets = extract_rows(await provider.list_assets(True), "assets")
    assets = select_assets(available_assets, requested_names)
    LOGGER.info(
        "MCP=%s | cuenta=%s | activos abiertos=%d | trading=%s",
        provider.mode,
        account,
        len(assets),
        provider.allow_writes,
    )
    if not assets:
        available_names = sorted(
            str(row.get("name", "")) for row in available_assets if row.get("name")
        )
        LOGGER.warning(
            "Ningún MCP_ASSETS coincide. Solicitados=%s | disponibles=%s",
            ", ".join(sorted(requested_names)),
            ", ".join(available_names[:30]) or "ninguno",
        )

    operations = 0
    for asset in assets:
        asset_id = int(asset["asset_id"])
        name = str(asset["name"])
        now = int(time.time())
        candles = normalize_candles(
            await provider.get_candles(asset_id, size=60, count=240), now
        )
        signal = get_signal(candles, "freedom")
        if signal is None or last_signals.get(asset_id) == signal.candle_time:
            continue
        last_signals[asset_id] = signal.candle_time
        LOGGER.info(
            "%s | Freedom %s | close=%.5f RSI=%.2f",
            name,
            signal.direction.upper(),
            signal.close,
            signal.rsi14,
        )
        if not provider.allow_writes:
            continue

        expiration = choose_expiration(
            list(asset.get("expirations") or []),
            signal.expiration_min or 5,
            now,
        )
        if expiration is None:
            LOGGER.warning("%s | sin expiración válida ofrecida; omitido", name)
            continue
        minimum = float(asset.get("minimum_amount", 0))
        maximum = float(asset.get("maximum_amount", float("inf")))
        if not minimum <= amount <= maximum:
            LOGGER.warning(
                "%s | monto %.2f fuera de rango [%.2f, %.2f]",
                name, amount, minimum, maximum,
            )
            continue

        result = await provider.place_trade(
            balance_id=int(balance["balance_id"]),
            balance_type=str(balance["type"]),
            asset_id=asset_id,
            direction=signal.direction,
            amount=amount,
            profit_percent=int(asset["profit_percent"]),
            expired=expiration,
        )
        LOGGER.info("%s | orden TRAINING enviada | %s", name, result)
        operations += 1
    return operations


async def run() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("mcp").setLevel(logging.WARNING)
    token = os.getenv("IQ_OPTION_MCP_TOKEN", "").strip()
    account = os.getenv("MCP_ACCOUNT", "TRAINING").strip().upper()
    if account not in {"TRAINING", "NORMAL"}:
        raise MCPConfigurationError("MCP_ACCOUNT debe ser TRAINING o NORMAL")

    trading_enabled = env_bool("MCP_TRADING_ENABLED")
    real_enabled = env_bool("MCP_REAL_ENABLED")
    if account == "NORMAL":
        if not real_enabled:
            raise MCPConfigurationError("NORMAL requiere MCP_REAL_ENABLED=true")
        if os.getenv("MCP_REAL_CONFIRMATION") != "I_UNDERSTAND_REAL_MONEY":
            raise MCPConfigurationError("Falta MCP_REAL_CONFIRMATION")

    provider = IQOptionMCPProvider(
        token,
        server="binary-options",
        allow_writes=trading_enabled,
        allow_real=real_enabled,
        timeout_seconds=float(os.getenv("MCP_TIMEOUT_SECONDS", "10")),
    )
    mode = await provider.initialize()
    if trading_enabled and mode != "read-write":
        raise MCPConfigurationError(
            f"El token reportó {mode}; no puede ejecutar place_trade"
        )

    names = {
        value.strip().upper()
        for value in os.getenv("MCP_ASSETS", "EURUSD-OTC").split(",")
        if value.strip()
    }
    amount = float(os.getenv("MCP_AMOUNT", "1"))
    run_once = env_bool("MCP_RUN_ONCE", True)
    interval = max(60.0, float(os.getenv("MCP_SCAN_INTERVAL_SECONDS", "60")))
    last_signals: dict[int, int] = {}

    while True:
        await scan_once(
            provider,
            account=account,
            amount=amount,
            requested_names=names,
            last_signals=last_signals,
        )
        if run_once:
            return
        await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(run())
