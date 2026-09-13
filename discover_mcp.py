"""Discover IQ Option MCP capabilities without invoking any tool."""

from __future__ import annotations

import argparse
import asyncio
import json
import os

from dotenv import load_dotenv

from mcp_discovery import ALLOWED_SERVERS, discover_server, discovery_to_dict


async def run(selected: str, timeout_seconds: float) -> int:
    token = os.getenv("IQ_OPTION_MCP_TOKEN", "").strip()
    servers = tuple(ALLOWED_SERVERS) if selected == "all" else (selected,)
    discoveries = []
    for server in servers:
        discovery = await discover_server(
            server,
            token,
            timeout_seconds=timeout_seconds,
        )
        discoveries.append(discovery_to_dict(discovery))
    print(json.dumps(discoveries, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Lista herramientas de IQ Option MCP sin ejecutar operaciones."
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
