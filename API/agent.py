"""API agent: wires the hand-written harness together."""
from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple

from shared.config import EFFORT, MODEL
from shared.domain import Domain

from .harness import loop
from .harness.history import History
from .harness.tokens import Meter

_USAGE_KEYS = ("input", "cache_read", "cache_write", "output", "calls", "cost_usd")


class HistoryMarker(NamedTuple):
    n_records: int
    digest: str


class APIAgent:
    def __init__(self, state_dir: str | Path, client: Any = None) -> None:
        if client is None:
            import anthropic
            client = anthropic.Anthropic(max_retries=4)
        self.client = client
        self.domain = Domain(state_dir, Path(state_dir) / "data")
        self.history = History(Path(state_dir) / "history.jsonl")
        self.meter = Meter()

    def turn(self, text: str) -> dict[str, Any]:
        result = loop.run_turn(self.client, MODEL, self.history, self.domain, self.meter, text, EFFORT)
        usage = self.meter.turns[-1]
        return {"text": result.text, "tools": result.tools_used, "stop_reason": result.stop_reason,
                **{k: usage[k] for k in _USAGE_KEYS}}

    def close(self) -> HistoryMarker:
        n = len(self.history.records)
        return HistoryMarker(n, self.history.fingerprint(n))

    def history_ok(self, marker: HistoryMarker) -> bool:
        """After a new instance's first turn: the earlier records are byte-identical and new ones were appended."""
        return (marker.n_records > 0 and len(self.history.records) > marker.n_records
                and self.history.fingerprint(marker.n_records) == marker.digest)
