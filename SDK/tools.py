"""SDK tools: the same shared/ domain code, exposed as an in-process MCP server."""
from __future__ import annotations

import logging
from typing import Any

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool  # replaces: harness/tools.py

from shared import domain as D

log = logging.getLogger(__name__)
SERVER_NAME = "dq"
ALLOWED = [f"mcp__{SERVER_NAME}__{name}" for name in D.SPECS]


def make_tool(domain: D.Domain, spec: D.ToolSpec) -> SdkMcpTool:
    @tool(spec.name, spec.description, spec.input_schema())  # replaces: harness/tools.py (schemas)
    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        try:
            return {"content": [{"type": "text", "text": D.call(domain, spec.name, args)}]}
        except D.ToolError as exc:  # replaces: harness/tools.py (is_error)
            return {"content": [{"type": "text", "text": str(exc)}], "is_error": True}
        except Exception:
            log.exception("tool %s crashed", spec.name)
            return {"content": [{"type": "text", "text": f"internal error in {spec.name}"}], "is_error": True}

    return handler


def build_server(domain: D.Domain) -> Any:
    return create_sdk_mcp_server(SERVER_NAME, tools=[make_tool(domain, spec) for spec in D.SPECS.values()])
