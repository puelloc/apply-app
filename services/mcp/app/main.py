"""MCP server entrypoint: build the API client + serve over streamable HTTP."""

from __future__ import annotations

import os
from pathlib import Path

from app.api import ApiClient
from app.server import build_server


def _token() -> str:
    token = os.environ.get("MCP_API_TOKEN")
    if token:
        return token
    path = Path("/run/secrets/mcp_api_token")
    if path.is_file():
        return path.read_text().strip()
    return ""


def main() -> None:
    client = ApiClient(os.environ["API_URL"], _token())
    server = build_server(client)
    server.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=8000,
        streamable_http_path="/mcp",
    )


if __name__ == "__main__":
    main()
