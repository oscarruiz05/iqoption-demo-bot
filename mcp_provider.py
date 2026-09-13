"""IQ Option MCP adapter with capability and account guards."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mcp_discovery import (
    ALLOWED_SERVERS,
    MCPConfigurationError,
    MCPDiscoveryError,
)

READ_TOOLS = {
    "get_capabilities",
    "get_limits",
    "get_candles",
    "get_trade_history",
    "list_assets",
    "list_balances",
    "list_positions",
}
WRITE_TOOLS = {"place_trade", "rollover_position", "sell_position"}


@dataclass(frozen=True)
class MCPAccessPolicy:
    server: str
    mode: str
    allow_writes: bool = False
    allow_real: bool = False

    def validate(self, tool_name: str, *, balance_type: str | None = None) -> None:
        if tool_name not in READ_TOOLS | WRITE_TOOLS:
            raise MCPConfigurationError(f"Herramienta MCP no permitida: {tool_name}")

        if tool_name not in WRITE_TOOLS:
            return

        if self.server != "binary-options":
            raise MCPConfigurationError(
                f"{self.server} no está autorizado para ejecutar operaciones"
            )
        if self.mode != "read-write":
            raise MCPConfigurationError(
                f"{self.server} reportó modo {self.mode}; se requiere read-write"
            )
        if not self.allow_writes:
            raise MCPConfigurationError(
                "Las operaciones MCP están deshabilitadas; activa MCP_TRADING_ENABLED"
            )

        normalized_balance = (balance_type or "").strip().lower()
        if normalized_balance not in {"training", "regular"}:
            raise MCPConfigurationError(
                "Debe verificarse el tipo de saldo antes de ejecutar una orden"
            )
        if normalized_balance == "regular" and not self.allow_real:
            raise MCPConfigurationError(
                "El saldo regular está bloqueado; activa MCP_REAL_ENABLED explícitamente"
            )


class IQOptionMCPProvider:
    """Small async client for the official binary-options MCP endpoint."""

    def __init__(
        self,
        token: str,
        *,
        server: str = "binary-options",
        allow_writes: bool = False,
        allow_real: bool = False,
        timeout_seconds: float = 10.0,
    ) -> None:
        if server not in ALLOWED_SERVERS:
            raise MCPConfigurationError(f"Servidor MCP no permitido: {server}")
        if not token.strip():
            raise MCPConfigurationError("Falta IQ_OPTION_MCP_TOKEN")
        self.token = token.strip()
        self.server = server
        self.timeout_seconds = timeout_seconds
        self.allow_writes = allow_writes
        self.allow_real = allow_real
        self.mode: str | None = None

    async def _call(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        try:
            import httpx2
            from mcp import Client
            from mcp.client.streamable_http import streamable_http_client
        except ImportError as exc:
            raise MCPConfigurationError(
                "Instala las dependencias con: pip install -r requirements.txt"
            ) from exc

        endpoint = ALLOWED_SERVERS[self.server]
        try:
            timeout = httpx2.Timeout(
                self.timeout_seconds, read=self.timeout_seconds
            )
            async with httpx2.AsyncClient(
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=timeout,
            ) as http_client:
                transport = streamable_http_client(
                    endpoint, http_client=http_client
                )
                async with Client(transport) as client:
                    result = await client.call_tool(tool_name, arguments)
                    if getattr(result, "is_error", False):
                        raise MCPDiscoveryError(
                            f"{self.server}.{tool_name} devolvió un error"
                        )
                    structured = getattr(result, "structured_content", None)
                    return structured if structured is not None else result
        except (MCPConfigurationError, MCPDiscoveryError):
            raise
        except Exception as exc:
            safe_message = str(exc).replace(self.token, "[REDACTED]")
            raise MCPDiscoveryError(
                f"Falló {self.server}.{tool_name}: {safe_message}"
            ) from exc

    async def initialize(self) -> str:
        capability = await self._call("get_capabilities", {})
        if isinstance(capability, dict):
            self.mode = str(capability.get("mode", "none")).lower()
        else:
            raise MCPDiscoveryError("Respuesta inválida de get_capabilities")
        return self.mode

    def _policy(self) -> MCPAccessPolicy:
        return MCPAccessPolicy(
            server=self.server,
            mode=self.mode or "none",
            allow_writes=self.allow_writes,
            allow_real=self.allow_real,
        )

    async def list_balances(self, types: str = "TRAINING") -> Any:
        self._policy().validate("list_balances")
        return await self._call("list_balances", {"types": types})

    async def list_assets(self, only_enabled: bool = True) -> Any:
        self._policy().validate("list_assets")
        return await self._call("list_assets", {"only_enabled": only_enabled})

    async def get_candles(
        self, asset_id: int, *, size: int = 60, count: int = 250
    ) -> Any:
        self._policy().validate("get_candles")
        return await self._call(
            "get_candles",
            {"asset_id": asset_id, "size": size, "count": count},
        )

    async def place_trade(
        self,
        *,
        balance_id: int,
        balance_type: str,
        asset_id: int,
        direction: str,
        amount: float,
        profit_percent: int,
        expired: int,
    ) -> Any:
        self._policy().validate("place_trade", balance_type=balance_type)
        normalized_direction = direction.strip().lower()
        if normalized_direction not in {"call", "put"}:
            raise MCPConfigurationError("direction debe ser call o put")
        if amount <= 0:
            raise MCPConfigurationError("amount debe ser mayor que cero")

        return await self._call(
            "place_trade",
            {
                "balance_id": balance_id,
                "asset_id": asset_id,
                "direction": normalized_direction,
                "amount": amount,
                "profit_percent": profit_percent,
                "expired": expired,
            },
        )
