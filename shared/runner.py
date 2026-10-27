"""Scenario runner shared by API/main.py and SDK/main.py: clean state, two sessions, state-based checks."""
from __future__ import annotations

import ast
import json
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Protocol

from shared import checks
from shared.config import EFFORT, MODEL
from shared.domain import ROOT, Domain

TOKEN_KEYS = ("input", "cache_read", "cache_write", "output", "calls", "cost_usd")


class Agent(Protocol):
    domain: Domain

    def turn(self, text: str) -> dict[str, Any]: ...
    def close(self) -> Any: ...
    def history_ok(self, marker: Any) -> bool: ...


def run(make_agent: Callable[[Path], Agent], scenario_path: str | Path, out_path: str | Path, label: str,
        count_lines: Callable[[], dict[str, int]]) -> dict[str, Any]:
    scenario = json.loads(Path(scenario_path).read_text("utf-8"))
    state = ROOT / "results" / f"_state_{label}"
    shutil.rmtree(state, ignore_errors=True)        # every run starts from clean state
    (state / "data").mkdir(parents=True)
    turns: list[dict[str, Any]] = []
    texts: dict[tuple[int, int], str] = {}
    marker, history_ok = None, False
    for session_no, session in enumerate(scenario["sessions"], 1):
        source = "orders.csv" if session["before"] == "load_day1" else "orders_day2.csv"
        shutil.copy(ROOT / "data" / source, state / "data" / "orders.csv")
        agent = make_agent(state)                   # fresh instance: loads persisted state from disk
        try:
            for turn_no, prompt in enumerate(session["turns"], 1):
                print(f"\n=== session {session_no} turn {turn_no}: {prompt}", flush=True)
                started = time.time()
                metrics = agent.turn(prompt)
                texts[(session_no, turn_no)] = metrics.pop("text")
                metrics.update(session=session_no, turn=turn_no, seconds=round(time.time() - started, 2), prompt=prompt)
                turns.append(metrics)
                if marker is not None and turn_no == 1:  # first turn of a later session: did history carry over?
                    history_ok = agent.history_ok(marker)
        finally:
            marker = agent.close()
    results = checks.evaluate(Domain(state, state / "data"), texts, history_ok)
    totals = {k: sum(t[k] for t in turns) for k in TOKEN_KEYS}
    prompt_tokens = totals["input"] + totals["cache_read"] + totals["cache_write"]
    totals["cache_hit_pct"] = round(100 * totals["cache_read"] / prompt_tokens, 1) if prompt_tokens else 0.0
    out = {"label": label, "model": MODEL, "effort": EFFORT, "turns": turns, "totals": totals, "checks": results,
           "checks_passed": f"{sum(results.values())}/{len(results)}", "harness_lines": count_lines()}
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(out, indent=1, ensure_ascii=False), "utf-8")
    print(f"\nchecks {out['checks_passed']}  cost=${totals['cost_usd']:.4f}  calls={totals['calls']}  "
          f"cache_hit={totals['cache_hit_pct']}%")
    for name, ok in results.items():
        print(("PASS " if ok else "FAIL ") + name)
    return out


def loc(path: str | Path) -> int:
    """Code lines: non-blank, not comment-only, and not inside a docstring (so docs don't inflate the count)."""
    source = Path(path).read_text("utf-8")
    docstring_lines: set[int] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and ast.get_docstring(node):
            first = node.body[0]
            docstring_lines.update(range(first.lineno, first.end_lineno + 1))
    return sum(1 for n, line in enumerate(source.splitlines(), 1)
               if line.strip() and not line.strip().startswith("#") and n not in docstring_lines)
