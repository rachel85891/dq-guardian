"""history.py: conversation persisted to disk as append-only JSONL."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import say


class History:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = self.path.read_text("utf-8") if self.path.exists() else ""
        self.records: list[dict[str, Any]] = [json.loads(line) for line in text.splitlines()]
        say("history.py", f"loaded {len(self.records)} records from {self.path.name}")

    def _write(self, record: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
        self.records.append(record)

    def append(self, message: dict[str, Any]) -> None:
        self._write({"msg": message})

    def append_compaction(self, summary: str) -> None:
        """Compaction is itself an appended record; earlier records are never rewritten."""
        self._write({"compact": summary, "upto": sum(1 for r in self.records if "msg" in r)})

    def messages(self) -> list[dict[str, Any]]:
        """The view sent to the model: latest summary (if any) followed by the messages after it."""
        msgs = [r["msg"] for r in self.records if "msg" in r]
        summaries = [r for r in self.records if "compact" in r]
        if not summaries:
            return msgs
        last = summaries[-1]
        head = {"role": "user", "content": f"<summary of earlier conversation>\n{last['compact']}\n</summary>"}
        return [head, *msgs[last["upto"]:]]

    def fingerprint(self, n_records: int) -> str:
        """Digest of the first n records as stored on disk; equal digests prove the prefix is unchanged."""
        lines = self.path.read_text("utf-8").splitlines()[:n_records]
        return hashlib.sha256("\n".join(lines).encode()).hexdigest()
