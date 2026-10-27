"""Each scenario check must be able to FAIL; otherwise "6/6" proves nothing."""
import pytest

from shared import checks
from shared.domain import call


@pytest.fixture
def good(domain):
    for col, rule, val in (("customer_id", "not_null", ""), ("amount", "min", "0"), ("order_id", "unique", "")):
        domain.add_rule("orders", col, rule, val)
    domain.remember("orders_owner", "Dana")
    domain.remember("severity_threshold", "high")
    domain.remember("severity_threshold", "medium")
    domain.log_incident("orders", "high", "dup")
    domain.log_incident("orders", "medium", "nulls")
    call(domain, "run_check", {"table": "orders"})              # day 1: duplicate order_id
    (domain.data / "orders.csv").write_text("order_id,customer_id,amount\n1,,5\n2,c,6\n")
    call(domain, "run_check", {"table": "orders"})              # day 2: only null customer_id
    return domain


TEXTS = {checks.RECALL_TURN: "The orders owner is Dana."}


def test_all_pass_on_good_state(good):
    assert all(checks.evaluate(good, TEXTS, True).values())


@pytest.mark.parametrize("mutate,failing", [
    (lambda d: d._save("rules", d.rules()[:1]), "rules_saved"),
    (lambda d: d.remember("severity_threshold", "high"), "contradiction_replaced_not_duplicated"),
    (lambda d: d._save("incidents", d.incidents()[:1]), "incidents_have_right_severity"),
    (lambda d: d.log_call("run_check", {}, "order_id|unique|1|rows:2\ncustomer_id|not_null|1|rows:1", False),
     "external_csv_reread_after_swap"),
    (lambda d: d._save("memory", [f for f in d.memory() if "owner" not in f["key"]]), "memory_survived_new_instance"),
])
def test_each_state_check_can_fail(good, mutate, failing):
    mutate(good)
    results = checks.evaluate(good, TEXTS, True)
    assert results[failing] is False and sum(results.values()) == len(results) - 1


def test_memory_check_needs_the_answer_to_contain_the_stored_value(good):
    assert checks.evaluate(good, {checks.RECALL_TURN: "I don't recall anything."}, True)["memory_survived_new_instance"] is False


def test_history_check_follows_flag(good):
    assert checks.evaluate(good, TEXTS, False)["history_continued"] is False
