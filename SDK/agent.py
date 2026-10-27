"""SDK agent: configuration only. Claude Code runs the loop."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage,
                              ToolUseBlock)

from shared.config import EFFORT, MODEL, SYSTEM_PROMPT
from shared.domain import Domain

from .tools import ALLOWED, SERVER_NAME, build_server


class SDKAgent:
    def __init__(self, state_dir: str | Path) -> None:
        self.state = Path(state_dir)
        self.domain = Domain(state_dir, self.state / "data")
        session_file = self.state / "session_id.txt"
        self.resume = session_file.read_text("utf-8").strip() if session_file.exists() else None
        self.session_id = self.resume
        self.loop = asyncio.new_event_loop()
        self.client = ClaudeSDKClient(ClaudeAgentOptions(
            model=MODEL, effort=EFFORT,
            system_prompt=SYSTEM_PROMPT,                        # replaces: harness/context.py (static part)
            tools=[],                                           # no built-in Claude Code tools
            allowed_tools=ALLOWED,
            mcp_servers={SERVER_NAME: build_server(self.domain)},
            strict_mcp_config=True,
            resume=self.resume,                                 # replaces: harness/history.py
            setting_sources=["project"], cwd=str(self.state),   # replaces: harness/memory.py (reads CLAUDE.md)
            max_turns=12,
        ))
        self._run(self.client.connect())

    def _run(self, coroutine: Any) -> Any:
        return self.loop.run_until_complete(coroutine)

    async def _turn(self, text: str) -> tuple[list[str], list[str], ResultMessage]:
        await self.client.query(text)
        tools_used: list[str] = []
        model_calls: set[str] = set()
        result = None
        async for message in self.client.receive_response():    # replaces: harness/loop.py
            if isinstance(message, AssistantMessage):
                model_calls.add(message.message_id or message.uuid or str(len(model_calls)))
                tools_used += [b.name.split("__")[-1] for b in message.content if isinstance(b, ToolUseBlock)]
            elif isinstance(message, ResultMessage):
                result = message
        if result is None:
            raise RuntimeError("SDK stream ended without a ResultMessage")
        return tools_used, sorted(model_calls), result

    def turn(self, text: str) -> dict[str, Any]:
        tools_used, model_calls, result = self._run(self._turn(text))
        if result.is_error:
            raise RuntimeError(f"SDK turn failed: {result.subtype} {result.errors}")
        usage = result.usage or {}                              # replaces: harness/tokens.py
        self.session_id = result.session_id
        (self.state / "session_id.txt").write_text(result.session_id, "utf-8")
        facts = "\n".join(f"- {f['key']}={f['value']}" for f in self.domain.active_facts())
        (self.state / "CLAUDE.md").write_text(f"# Saved facts\n{facts}\n", "utf-8")  # replaces: harness/memory.py (write side)
        return {"text": result.result or "", "tools": tools_used, "stop_reason": result.stop_reason,
                "input": usage.get("input_tokens", 0), "cache_read": usage.get("cache_read_input_tokens", 0),
                "cache_write": usage.get("cache_creation_input_tokens", 0), "output": usage.get("output_tokens", 0),
                "calls": len(model_calls), "cost_usd": result.total_cost_usd or 0.0}

    def close(self) -> str | None:
        try:
            self._run(self.client.disconnect())
        finally:
            self.loop.close()
        return self.session_id

    def history_ok(self, marker: str | None) -> bool:
        """After the new instance's first turn: the same Claude Code session continued."""
        return bool(marker) and self.resume == marker and self.session_id == marker
