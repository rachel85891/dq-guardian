"""compaction.py: summarize the whole conversation once the prompt passes a threshold."""
from __future__ import annotations

from typing import Any

from . import say
from .history import History
from .tokens import Meter

THRESHOLD_TOKENS = 40_000
_ASK = "Summarize this conversation: rules, incidents, saved facts, open questions. Be dense. Do not call tools."


def maybe_compact(client: Any, model: str, history: History, meter: Meter, tools: list[dict], system: list[dict],
                  threshold: int = THRESHOLD_TOKENS) -> bool:
    prompt_tokens = meter.last_prompt_size()
    if prompt_tokens < threshold:
        return False
    say("compaction.py", f"prompt {prompt_tokens} >= {threshold}: summarizing")
    # tools must be declared because the history contains tool_use/tool_result blocks; tool_choice none forbids calls.
    response = client.messages.create(
        model=model, max_tokens=1500, system=system, tools=tools, tool_choice={"type": "none"},
        messages=[*history.messages(), {"role": "user", "content": _ASK}],
    )
    meter.add(response.usage)
    history.append_compaction("".join(b.text for b in response.content if b.type == "text"))
    return True
