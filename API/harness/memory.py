"""memory.py: which saved facts are pulled into a turn (the rest stay reachable via the recall tool)."""
from __future__ import annotations

import re

from shared.domain import Domain

from . import say

_STOPWORDS = frozenset("the and for you are with what that this have was not but all can who how why".split())


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in _STOPWORDS}


def relevant_facts(domain: Domain, user_text: str, limit: int = 4) -> list[str]:
    """Active facts sharing at least one whole word with the user's message, best matches first."""
    query = _words(user_text)
    facts = domain.active_facts()
    scored = [(len(query & _words(f"{f['key']} {f['value']}")), f) for f in facts]
    picked = [f for score, f in sorted(scored, key=lambda pair: -pair[0]) if score > 0][:limit]
    say("memory.py", f"{len(picked)}/{len(facts)} active facts relevant")
    return [f"{f['key']}={f['value']}" for f in picked]
