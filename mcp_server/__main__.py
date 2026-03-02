"""Allow running as `python -m mcp_server`."""

import sys

from mcp_server.server import _AUTH_TOKEN, _is_http, mcp

if _is_http and not _AUTH_TOKEN:
    print(
        "ERROR: MCP_AUTH_TOKEN is required for HTTP transport. "
        "Set MCP_AUTH_TOKEN env var before starting the server remotely.",
        file=sys.stderr,
    )
    sys.exit(1)

transport = "streamable-http" if _is_http else "stdio"
mcp.run(transport=transport)
