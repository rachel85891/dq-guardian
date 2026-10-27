"""context.py: what goes into each turn.

The static system prompt is cached. Per-turn context (relevant facts, open-incident count) rides in the
user message instead, so it never invalidates the cached prefix.
"""
from __future__ import annotations

from typing import Any

from shared.config import SYSTEM_PROMPT
from shared.domain import Domain

from . import memory, say

SYSTEM: list[dict[str, Any]] = [{"type": "text", "text": SYSTEM_PROMPT}]


def build_user_content(domain: Domain, user_text: str) -> list[dict[str, Any]]:
    facts = memory.relevant_facts(domain, user_text)
    open_incidents = sum(1 for i in domain.incidents() if i["status"] == "open")
    body = "\n".join(facts) if facts else "no relevant saved facts (use recall for more)"
    say("context.py", f"injected {len(facts)} facts + open_incidents={open_incidents}")
    return [{"type": "text", "text": f"<context open_incidents={open_incidents}>\n{body}\n</context>\n\n{user_text}"}]
