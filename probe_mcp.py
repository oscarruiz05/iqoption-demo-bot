"""Run safe read-only IQ Option MCP capability probes."""

from __future__ import annotations

import argparse
import asyncio
import json
import os

from dotenv import load_dotenv

from mcp_discovery import ALLOWED_SERVERS, call_read_only_tool


async def run(selected: str, timeout_seconds: float) -> int:
    token = os.getenv("IQ_OPTION_MCP_TOKEN", "").strip()
    servers = tuple(ALLOWED_SERVERS) if selected == "all" else (selected,)
    output = []
    for server in servers:
        values = {"server": server}
        for tool_name in ("get_capabilities", "get_limits"):
            values[tool_name] = await call_read_only_tool(
                server,
                token,
                tool_name,
                timeout_seconds=timeout_seconds,
            )
        output.append(values)
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Consulta capacidades y límites MCP sin operar."
    )
    parser.add_argument(
        "--server",
        choices=("turbo-options", "binary-options", "all"),
        default="all",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.getenv("MCP_TIMEOUT_SECONDS", "10")),
    )
    args = parser.parse_args()
    return asyncio.run(run(args.server, args.timeout))


if __name__ == "__main__":
    raise SystemExit(main())
