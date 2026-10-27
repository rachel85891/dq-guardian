"""Whole scenario through the real runner with a scripted model (proves plumbing, not model quality)."""
import json
import shutil

from conftest import ROOT, FakeClient, resp, text, tool_use

from API.agent import APIAgent
from shared import runner


def rounds(final, *calls):
    return [resp([tool_use(i, n, **a) for i, (n, a) in enumerate(calls)], "tool_use"), resp([text(final)], "end_turn")]


def script(contradiction_key="severity_threshold"):
    def add(col, rule, val=""):
        return ("add_rule", {"table": "orders", "column": col, "rule": rule, "value": val})

    steps = [
        rounds("profiled", ("profile_table", {"table": "orders"})),
        rounds("rules set", add("customer_id", "not_null"), add("amount", "min", "0"), add("order_id", "unique"),
               ("run_check", {"table": "orders"})),
        rounds("saved", ("remember", {"key": "orders_owner", "value": "Dana"}),
               ("remember", {"key": "severity_threshold", "value": "high"}),
               ("log_incident", {"table": "orders", "severity": "high", "summary": "dup"})),
        rounds("Owner: Dana", ("recall", {"query": "orders"})),
        rounds("rechecked", ("run_check", {"table": "orders"})),
        rounds("updated", ("remember", {"key": contradiction_key, "value": "medium"})),
        rounds("logged", ("log_incident", {"table": "orders", "severity": "medium", "summary": "nulls"})),
        rounds("listed", ("list_incidents", {})),
    ]
    return [r for step in steps for r in step]


def run_scenario(tmp_path, label, client):
    try:
        return runner.run(lambda state: APIAgent(state, client), ROOT / "scenario.json", tmp_path / "out.json", label, lambda: {})
    finally:
        shutil.rmtree(ROOT / "results" / f"_state_{label}", ignore_errors=True)


def test_scenario_passes_with_correct_model_behaviour(tmp_path):
    result = run_scenario(tmp_path, "t_ok", FakeClient(script()))
    assert result["checks_passed"] == "6/6", result["checks"]
    saved = json.loads((tmp_path / "out.json").read_text())
    assert len(saved["turns"]) == 8 and saved["turns"][0]["calls"] == 2 and "cache_hit_pct" in saved["totals"]


def test_scenario_fails_when_contradiction_is_stored_under_a_new_key(tmp_path):
    result = run_scenario(tmp_path, "t_bad", FakeClient(script(contradiction_key="severity_level")))
    assert result["checks"]["contradiction_replaced_not_duplicated"] is False
    assert result["checks_passed"] != "6/6"
