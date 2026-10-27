"""tools.py: JSON schemas, dispatch, and failures returned to the model as is_error."""
from __future__ import annotations

import logging
from typing import Any

from shared import domain as D

from . import say

log = logging.getLogger(__name__)
SCHEMAS = D.tool_schemas()


def run_tool_uses(domain: D.Domain, content: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Execute every tool_use block; return ALL tool_results for a single user message."""
    results = []
    for block in (b for b in content if b["type"] == "tool_use"):
        try:
            output, failed = D.call(domain, block["name"], block["input"]), False
        except D.ToolError as exc:
            output, failed = str(exc), True
        except Exception:  # a bug in a tool must not kill the agent loop; the model is told and the trace is kept
            log.exception("tool %s crashed", block["name"])
            output, failed = f"internal error in {block['name']}", True
        say("tools.py", f"{block['name']}({block['input']}) -> {'ERROR ' if failed else ''}{output[:60]!r}")
        result = {"type": "tool_result", "tool_use_id": block["id"], "content": output}
        if failed:
            result["is_error"] = True
        results.append(result)
    return results
