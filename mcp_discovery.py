"""Read-only discovery client for IQ Option MCP servers.

This module deliberately exposes no order execution method. Tool names and schemas
must be discovered and reviewed before wiring financial actions into the bot.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse


ALLOWED_SERVERS = {
    "turbo-options": "https://turbo-options.mcp.iqoption.com",
    "binary-options": "https://binary-options.mcp.iqoption.com",
}
WRITE_HINTS = (
    "buy", "sell", "order", "trade", "position", "execute", "purchase", "open", "close"
)


class MCPConfigurationError(ValueError):
    pass


class MCPDiscoveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class DiscoveredTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    potentially_writes: bool


@dataclass(frozen=True)
class ServerDiscovery:
    server: str
    url: str
    protocol_version: str | None
    server_name: str | None
    tools: tuple[DiscoveredTool, ...]


def validate_server_url(server: str, url: str) -> str:
    expected = ALLOWED_SERVERS.get(server)
    if expected is None:
        raise MCPConfigurationError(f"Servidor MCP no permitido: {server}")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.username or parsed.password:
        raise MCPConfigurationError("La URL MCP debe usar HTTPS y no incluir credenciales")
    if url.rstrip("/") != expected:
        raise MCPConfigurationError(
            f"URL inesperada para {server}; se esperaba {expected}"
        )
    return expected


def classify_tool(name: str, description: str = "") -> bool:
    text = f"{name} {description}".lower()
    return any(hint in text for hint in WRITE_HINTS)


def _model_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, dict):
        return value
    return {"value": str(value)}


async def discover_server(
    server: str,
    token: str,
    *,
    url: str | None = None,
    timeout_seconds: float = 10.0,
) -> ServerDiscovery:
    """Connect and list tools only; no MCP tool is invoked."""
    if not token.strip():
        raise MCPConfigurationError("Falta IQ_OPTION_MCP_TOKEN")
    if timeout_seconds <= 0:
        raise MCPConfigurationError("MCP_TIMEOUT_SECONDS debe ser mayor que cero")

    endpoint = validate_server_url(server, url or ALLOWED_SERVERS.get(server, ""))

    try:
        import httpx2
        from mcp import Client
        from mcp.client.streamable_http import streamable_http_client
    except ImportError as exc:
        raise MCPConfigurationError(
            'Instala las dependencias con: pip install -r requirements.txt'
        ) from exc

    headers = {"Authorization": f"Bearer {token}"}
    try:
        timeout = httpx2.Timeout(timeout_seconds, read=timeout_seconds)
        async with httpx2.AsyncClient(headers=headers, timeout=timeout) as http_client:
            transport = streamable_http_client(endpoint, http_client=http_client)
            async with Client(transport) as client:
                result = await client.list_tools()
                tools = tuple(
                    DiscoveredTool(
                        name=tool.name,
                        description=tool.description or "",
                        input_schema=_model_dict(tool.input_schema),
                        potentially_writes=classify_tool(
                            tool.name, tool.description or ""
                        ),
                    )
                    for tool in result.tools
                )
                server_info = _model_dict(client.server_info)
                return ServerDiscovery(
                    server=server,
                    url=endpoint,
                    protocol_version=(
                        str(client.protocol_version)
                        if client.protocol_version is not None
                        else None
                    ),
                    server_name=server_info.get("name"),
                    tools=tools,
                )
    except MCPConfigurationError:
        raise
    except Exception as exc:
        # Never include request headers or the bearer token in the error.
        message = str(exc).replace(token, "[REDACTED]")
        raise MCPDiscoveryError(
            f"No se pudo descubrir {server}: {message}"
        ) from exc


def discovery_to_dict(discovery: ServerDiscovery) -> dict[str, Any]:
    return {
        "server": discovery.server,
        "url": discovery.url,
        "protocol_version": discovery.protocol_version,
        "server_name": discovery.server_name,
        "tools": [asdict(tool) for tool in discovery.tools],
    }
