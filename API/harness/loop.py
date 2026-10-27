"""loop.py: run while stop_reason == 'tool_use'; all tool_results go back in one message."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shared.domain import Domain

from . import caching, compaction, context, say, tools
from .history import History
from .tokens import Meter

MAX_STEPS = 12
MAX_TOKENS = 4096


class StepLimitExceeded(RuntimeError):
    """The model kept calling tools for MAX_STEPS rounds in a single turn."""


@dataclass
class TurnResult:
    text: str
    tools_used: list[str] = field(default_factory=list)
    stop_reason: str = "end_turn"


def run_turn(client: Any, model: str, history: History, domain: Domain, meter: Meter, user_text: str,
             effort: str = "medium") -> TurnResult:
    meter.start()
    try:
        compaction.maybe_compact(client, model, history, meter, tools.SCHEMAS, context.SYSTEM)
        history.append({"role": "user", "content": context.build_user_content(domain, user_text)})
        return _converse(client, model, history, domain, meter, effort)
    except Exception as exc:
        # Keep roles alternating so a later turn can still be sent (every tool_use is answered before any raise).
        messages = history.messages()
        if messages and messages[-1]["role"] == "user":
            history.append({"role": "assistant", "content": [{"type": "text", "text": f"[turn aborted: {exc!r}]"}]})
        raise
    finally:
        meter.finish()


def _converse(client: Any, model: str, history: History, domain: Domain, meter: Meter, effort: str) -> TurnResult:
    used: list[str] = []
    for _ in range(MAX_STEPS):
        schemas, system, messages = caching.apply(tools.SCHEMAS, context.SYSTEM, history.messages())
        say("loop.py", f"model call #{meter.cur['calls'] + 1}")
        response = client.messages.create(model=model, max_tokens=MAX_TOKENS, tools=schemas, system=system,
                                          messages=messages, output_config={"effort": effort})
        meter.add(response.usage)
        content = [b.model_dump(exclude_none=True) for b in response.content]  # thinking blocks kept verbatim
        history.append({"role": "assistant", "content": content})
        calls = [b for b in content if b["type"] == "tool_use"]
        if response.stop_reason == "tool_use":
            used += [b["name"] for b in calls]
            history.append({"role": "user", "content": tools.run_tool_uses(domain, content)})
            continue
        if calls:  # cut off (max_tokens/refusal) mid tool call: answer it so the history stays valid
            note = f"not executed: response ended with stop_reason={response.stop_reason}"
            history.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": b["id"], "content": note, "is_error": True} for b in calls]})
        say("loop.py", f"stop_reason={response.stop_reason}")
        text = "".join(b["text"] for b in content if b["type"] == "text")
        return TurnResult(text, used, response.stop_reason)
    raise StepLimitExceeded(f"no final answer after {MAX_STEPS} model calls")
