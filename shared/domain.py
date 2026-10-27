"""DQ Guardian domain: tool functions over JSON state and CSV files. No LLM code lives here.

Tools return compact pipe-separated strings on purpose: that is what the model reads, and every
character costs tokens. Structured accessors (rules(), incidents(), memory(), tool_log()) exist for
tests and scenario checks.
"""
from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

RULE_KINDS = ("not_null", "unique", "min", "max")
SEVERITIES = ("low", "medium", "high")
_TABLE_NAME = re.compile(r"[A-Za-z0-9_]+")
_MAX_ROWS_SHOWN = 5


class ToolError(Exception):
    """Raised for any failed tool call; the message is shown to the model."""


class Domain:
    """State (JSON files in `state_dir`) plus CSV tables (in `data_dir`).

    Single-process only: writes are atomic (replace) but there is no cross-process locking.
    """

    def __init__(self, state_dir: str | Path, data_dir: str | Path | None = None) -> None:
        self.state = Path(state_dir)
        self.state.mkdir(parents=True, exist_ok=True)
        self.data = Path(data_dir) if data_dir else ROOT / "data"

    # ---- storage (one seam, so JSON can become SQLite without touching the tools) ----
    def _load(self, name: str) -> list[dict[str, Any]]:
        path = self.state / f"{name}.json"
        return json.loads(path.read_text("utf-8")) if path.exists() else []

    def _save(self, name: str, records: list[dict[str, Any]]) -> None:
        path = self.state / f"{name}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(records, indent=1), "utf-8")
        os.replace(tmp, path)

    def _rows(self, table: str) -> list[dict[str, str]]:
        if not _TABLE_NAME.fullmatch(table):
            raise ToolError(f"invalid table name {table!r}: use letters, digits, underscore")
        path = self.data / f"{table}.csv"
        if not path.is_file():
            raise ToolError(f"unknown table '{table}'")
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    # ---- structured accessors (tests, checks) ----
    def rules(self) -> list[dict[str, Any]]:
        return self._load("rules")

    def incidents(self) -> list[dict[str, Any]]:
        return self._load("incidents")

    def memory(self) -> list[dict[str, Any]]:
        return self._load("memory")

    def active_facts(self) -> list[dict[str, Any]]:
        return [fact for fact in self.memory() if fact["active"]]

    def tool_log(self) -> list[dict[str, Any]]:
        path = self.state / "tool_log.jsonl"
        return [json.loads(line) for line in path.read_text("utf-8").splitlines()] if path.exists() else []

    def log_call(self, name: str, args: dict[str, Any], result: str, error: bool) -> None:
        entry = {"tool": name, "args": args, "result": result, "error": error}
        with (self.state / "tool_log.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    # ---- tools ----
    def profile_table(self, table: str) -> str:
        """EXTERNAL tool: reads the CSV from disk on every call."""
        rows = self._rows(table)
        columns = list(rows[0]) if rows else []
        nulls = ",".join(f"{col}={sum(1 for row in rows if row[col] == '')}" for col in columns)
        return f"rows={len(rows)}|cols={','.join(columns)}|nulls:{nulls}"

    def add_rule(self, table: str, column: str, rule: str, value: str = "") -> str:
        if rule not in RULE_KINDS:
            raise ToolError(f"rule must be one of {'|'.join(RULE_KINDS)}")
        if rule in ("min", "max"):
            try:
                float(value)
            except ValueError:
                raise ToolError(f"rule '{rule}' needs a numeric value, got {value!r}") from None
        rows = self._rows(table)
        if rows and column not in rows[0]:
            raise ToolError(f"table '{table}' has no column '{column}'")
        key = (table, column, rule)
        kept = [r for r in self.rules() if (r["table"], r["column"], r["rule"]) != key]
        kept.append({"table": table, "column": column, "rule": rule, "value": str(value)})
        self._save("rules", kept)
        return f"ok|{table}.{column}.{rule}={value}"

    def list_rules(self, table: str = "") -> str:
        rules = [r for r in self.rules() if not table or r["table"] == table]
        return "\n".join(f"{r['table']}|{r['column']}|{r['rule']}|{r['value']}" for r in rules) or "none"

    def run_check(self, table: str) -> str:
        rows = self._rows(table)
        lines = []
        for rule in (r for r in self.rules() if r["table"] == table):
            if rows and rule["column"] not in rows[0]:  # schema drift must not look like "every cell is null"
                lines.append(f"{rule['column']}|{rule['rule']}|missing_column")
                continue
            bad = _violations(rule, [row[rule["column"]] for row in rows])
            if bad:
                shown = ",".join(map(str, bad[:_MAX_ROWS_SHOWN]))
                lines.append(f"{rule['column']}|{rule['rule']}|{len(bad)}|rows:{shown}")
        return "\n".join(lines) or "pass"

    def log_incident(self, table: str, severity: str, summary: str) -> str:
        if severity not in SEVERITIES:
            raise ToolError(f"severity must be one of {'|'.join(SEVERITIES)}")
        incidents = self.incidents()
        incident_id = len(incidents) + 1
        incidents.append({"id": incident_id, "table": table, "severity": severity, "summary": summary, "status": "open"})
        self._save("incidents", incidents)
        return f"ok|incident {incident_id}"

    def list_incidents(self, status: str = "open") -> str:
        shown = [i for i in self.incidents() if status == "all" or i["status"] == status]
        return "\n".join(f"{i['id']}|{i['table']}|{i['severity']}|{i['summary']}" for i in shown) or "none"

    def remember(self, key: str, value: str) -> str:
        """Save a fact. An existing active fact with the same key is kept but marked superseded."""
        facts = self.memory()
        for fact in facts:
            if fact["key"] == key and fact["active"]:
                fact["active"] = False
        facts.append({"key": key, "value": str(value), "active": True})
        self._save("memory", facts)
        return f"ok|{key}={value}"

    def recall(self, query: str = "") -> str:
        needle = query.lower()
        hits = [f for f in self.active_facts() if needle in f["key"].lower() or needle in f["value"].lower()]
        return "\n".join(f"{f['key']}={f['value']}" for f in hits) or "none"


def _violations(rule: dict[str, Any], values: list[str]) -> list[int]:
    """1-based data-row numbers that break `rule`. Empty cells are only judged by not_null."""
    kind = rule["rule"]
    if kind == "not_null":
        return [i for i, v in enumerate(values, 1) if v == ""]
    if kind == "unique":
        seen: set[str] = set()
        bad = []
        for i, v in enumerate(values, 1):
            if v == "":
                continue
            if v in seen:
                bad.append(i)
            seen.add(v)
        return bad
    limit = float(rule["value"])
    bad = []
    for i, v in enumerate(values, 1):
        if v == "":
            continue
        try:
            number = float(v)
        except ValueError:
            bad.append(i)  # non-numeric cell breaks a numeric bound
            continue
        if (kind == "min" and number < limit) or (kind == "max" and number > limit):
            bad.append(i)
    return bad


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    required: tuple[str, ...]
    optional: tuple[str, ...] = ()

    def input_schema(self) -> dict[str, Any]:
        props = {p: {"type": "string"} for p in (*self.required, *self.optional)}
        return {"type": "object", "properties": props, "required": list(self.required), "additionalProperties": False}


SPECS: dict[str, ToolSpec] = {s.name: s for s in (
    ToolSpec("profile_table", "Read a CSV table from disk: row count, columns, null counts per column.", ("table",)),
    ToolSpec("add_rule", "Add a data-quality rule (not_null|unique|min|max) on a column; min/max need a numeric value. "
             "Re-adding the same rule replaces it.", ("table", "column", "rule"), ("value",)),
    ToolSpec("list_rules", "List rules, optionally for one table.", (), ("table",)),
    ToolSpec("run_check", "Run all rules of a table against its current CSV. Returns violations or 'pass'.", ("table",)),
    ToolSpec("log_incident", "Open a data-quality incident. severity: low|medium|high.", ("table", "severity", "summary")),
    ToolSpec("list_incidents", "List incidents. status=open|all (default open).", (), ("status",)),
    ToolSpec("remember", "Save a durable fact or preference. Same key replaces the old value (old one is kept as superseded).",
             ("key", "value")),
    ToolSpec("recall", "Search saved facts by substring of key/value.", (), ("query",)),
)}


def tool_schemas() -> list[dict[str, Any]]:
    return [{"name": s.name, "description": s.description, "input_schema": s.input_schema()} for s in SPECS.values()]


def call(domain: Domain, name: str, args: dict[str, Any]) -> str:
    """Single dispatch point for both harnesses. Logs every call; raises ToolError on failure."""
    try:
        if name not in SPECS:
            raise ToolError(f"unknown tool {name}")
        result = getattr(domain, name)(**args)
    except ToolError as exc:
        domain.log_call(name, args, str(exc), error=True)
        raise
    except TypeError as exc:  # wrong/missing arguments from the model
        domain.log_call(name, args, str(exc), error=True)
        raise ToolError(f"bad arguments for {name}: {exc}") from exc
    domain.log_call(name, args, result, error=False)
    return result
