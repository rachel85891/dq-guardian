"""Pass/fail checks for scenario.json, evaluated on persisted state (not on answer wording)."""
from __future__ import annotations

from typing import Callable

from shared.domain import Domain

Check = Callable[[Domain, dict[tuple[int, int], str], bool], bool]

RECALL_TURN = (2, 1)  # (session, turn) of "what do you remember ...?" in scenario.json


def rules_saved(domain: Domain, texts: dict, history_ok: bool) -> bool:
    got = {f"{r['column']}.{r['rule']}" for r in domain.rules() if r["table"] == "orders"}
    return {"customer_id.not_null", "amount.min", "order_id.unique"} <= got


def contradiction_replaced_not_duplicated(domain: Domain, texts: dict, history_ok: bool) -> bool:
    sev = [f for f in domain.memory() if f["key"] == "severity_threshold"]
    active = [f for f in sev if f["active"]]
    superseded = [f for f in sev if not f["active"]]
    return len(active) == 1 and active[0]["value"] == "medium" and any(f["value"] == "high" for f in superseded)


def incidents_have_right_severity(domain: Domain, texts: dict, history_ok: bool) -> bool:
    return sorted(i["severity"] for i in domain.incidents()) == ["high", "medium"]


def external_csv_reread_after_swap(domain: Domain, texts: dict, history_ok: bool) -> bool:
    runs = [e["result"] for e in domain.tool_log() if e["tool"] == "run_check" and not e["error"]]
    if len(runs) < 2:
        return False
    first, last = runs[0], runs[-1]
    return "order_id|unique" in first and "order_id|unique" not in last and "customer_id|not_null" in last


def memory_survived_new_instance(domain: Domain, texts: dict, history_ok: bool) -> bool:
    """The saved owner is in persisted memory AND session 2 repeated it without being told."""
    owner = [f["value"] for f in domain.active_facts() if "owner" in f["key"]]
    return bool(owner) and any(o.lower() in texts.get(RECALL_TURN, "").lower() for o in owner)


def history_continued(domain: Domain, texts: dict, history_ok: bool) -> bool:
    return history_ok


ALL: dict[str, Check] = {f.__name__: f for f in (
    rules_saved, contradiction_replaced_not_duplicated, incidents_have_right_severity,
    external_csv_reread_after_swap, memory_survived_new_instance, history_continued)}


def evaluate(domain: Domain, texts: dict[tuple[int, int], str], history_ok: bool) -> dict[str, bool]:
    return {name: bool(check(domain, texts, history_ok)) for name, check in ALL.items()}
