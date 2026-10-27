"""tokens.py: per-turn usage and cost."""
from __future__ import annotations

from typing import Any

from . import say

# USD per million tokens for claude-opus-5-5. Cache write is the 5-minute TTL rate (1.25x input).
PRICE_PER_MTOK = {"input": 4.0, "output": 20.0, "cache_read": 0.20, "cache_write": 5.0}


class Meter:
    """Accumulates usage over every model call of a turn (including compaction)."""

    def __init__(self) -> None:
        self.turns: list[dict[str, Any]] = []
        self.cur: dict[str, Any] = {}

    def start(self) -> None:
        self.cur = {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0, "calls": 0, "last_prompt": 0}

    def add(self, usage: Any) -> None:
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        c = self.cur
        c["input"] += usage.input_tokens or 0
        c["cache_read"] += cache_read
        c["cache_write"] += cache_write
        c["output"] += usage.output_tokens or 0
        c["calls"] += 1
        c["last_prompt"] = (usage.input_tokens or 0) + cache_read + cache_write
        say("tokens.py", f"call {c['calls']}: in={usage.input_tokens} cache_read={cache_read} "
                         f"cache_write={cache_write} out={usage.output_tokens}")

    def finish(self) -> dict[str, Any]:
        self.cur["cost_usd"] = sum(self.cur[k] * PRICE_PER_MTOK[k] for k in PRICE_PER_MTOK) / 1e6
        self.turns.append(self.cur)
        return self.cur

    def last_prompt_size(self) -> int:
        """Prompt size of the final model call of the previous finished turn."""
        return self.turns[-1]["last_prompt"] if self.turns else 0
