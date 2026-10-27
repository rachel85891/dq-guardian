"""caching.py: where cache_control breakpoints go (render order: tools -> system -> messages)."""
from __future__ import annotations

import copy
from typing import Any

from . import say

_EPHEMERAL = {"type": "ephemeral"}


def apply(tools: list[dict], system: list[dict], messages: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Return request copies with 3 breakpoints; the stored history is never mutated."""
    tools = copy.deepcopy(tools)
    tools[-1]["cache_control"] = _EPHEMERAL         # whole tool list
    system = copy.deepcopy(system)
    system[-1]["cache_control"] = _EPHEMERAL        # static system prompt
    tail = copy.deepcopy(messages[-1])              # only the last message needs copying
    blocks: Any = tail["content"]
    if isinstance(blocks, str):
        blocks = tail["content"] = [{"type": "text", "text": blocks}]
    blocks[-1]["cache_control"] = _EPHEMERAL        # rolling breakpoint at the conversation tail
    say("caching.py", "breakpoints: tools, system, last message block")
    return tools, system, [*messages[:-1], tail]
