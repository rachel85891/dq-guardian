import json

import pytest

from shared import domain as D


def test_profile_reads_csv(domain):
    out = domain.profile_table("orders")
    assert out.startswith("rows=6|") and "customer_id=1" in out and "amount=1" in out


@pytest.mark.parametrize("name", ["../secret", "..\\secret", "a/b", "", "orders.csv", "x y"])
def test_table_name_cannot_escape_data_dir(domain, name):
    (domain.state / "secret.csv").write_text("a\n1\n")
    with pytest.raises(D.ToolError):
        domain.profile_table(name)


def test_unknown_table_is_logged_as_error(domain):
    with pytest.raises(D.ToolError):
        D.call(domain, "profile_table", {"table": "nope"})
    assert domain.tool_log()[-1]["error"] is True


def test_bad_arguments_become_tool_error(domain):
    with pytest.raises(D.ToolError, match="bad arguments"):
        D.call(domain, "profile_table", {"tabel": "orders"})
    with pytest.raises(D.ToolError, match="unknown tool"):
        D.call(domain, "drop_database", {})


def test_empty_csv(domain):
    (domain.data / "empty.csv").write_text("a,b\n")
    assert domain.profile_table("empty") == "rows=0|cols=|nulls:"
    assert domain.run_check("empty") == "pass"


def test_rules_and_check(domain):
    domain.add_rule("orders", "customer_id", "not_null")
    domain.add_rule("orders", "amount", "min", "0")
    domain.add_rule("orders", "order_id", "unique")
    out = domain.run_check("orders")
    assert "customer_id|not_null|1" in out and "amount|min|1" in out and "order_id|unique|1" in out


def test_unique_ignores_nulls(domain):
    (domain.data / "t.csv").write_text("x\n\n\n1\n")
    domain.add_rule("t", "x", "unique")
    assert domain.run_check("t") == "pass"


def test_non_numeric_cell_breaks_numeric_bound(domain):
    (domain.data / "t.csv").write_text("x\n5\nabc\n")
    domain.add_rule("t", "x", "max", "10")
    assert domain.run_check("t") == "x|max|1|rows:2"


@pytest.mark.parametrize("rule,value", [("min", ""), ("max", "abc"), ("regex", "x")])
def test_add_rule_validates_before_saving(domain, rule, value):
    with pytest.raises(D.ToolError):
        domain.add_rule("orders", "amount", rule, value)
    assert domain.rules() == []        # nothing broken was persisted


def test_add_rule_rejects_unknown_column(domain):
    with pytest.raises(D.ToolError, match="no column"):
        domain.add_rule("orders", "nope", "not_null")


def test_add_rule_replaces_same_rule(domain):
    domain.add_rule("orders", "amount", "min", "0")
    domain.add_rule("orders", "amount", "min", "10")
    assert domain.list_rules("orders") == "orders|amount|min|10"


def test_remember_supersedes_instead_of_deleting(domain):
    domain.remember("severity_threshold", "high")
    domain.remember("severity_threshold", "medium")
    assert domain.recall("severity") == "severity_threshold=medium"
    assert [(f["value"], f["active"]) for f in domain.memory()] == [("high", False), ("medium", True)]


def test_check_rereads_file(domain):
    domain.add_rule("orders", "order_id", "unique")
    assert "unique" in domain.run_check("orders")
    (domain.data / "orders.csv").write_text("order_id\n1\n2\n")
    assert domain.run_check("orders") == "pass"


def test_incidents_and_severity_validation(domain):
    domain.log_incident("orders", "high", "dup ids")
    assert domain.list_incidents() == "1|orders|high|dup ids"
    with pytest.raises(D.ToolError):
        domain.log_incident("orders", "catastrophic", "x")
    assert len(domain.incidents()) == 1


def test_save_is_atomic_no_tmp_left(domain):
    domain.remember("k", "v")
    assert not list(domain.state.glob("*.tmp")) and json.loads((domain.state / "memory.json").read_text())


def test_schemas_cover_all_tools():
    names = {s["name"] for s in D.tool_schemas()}
    assert names == set(D.SPECS) and len(names) >= 3
    add_rule = next(s for s in D.tool_schemas() if s["name"] == "add_rule")["input_schema"]
    assert add_rule["required"] == ["table", "column", "rule"] and "value" in add_rule["properties"]


def test_missing_column_is_reported_not_treated_as_all_null(domain):
    domain.add_rule("orders", "customer_id", "not_null")
    (domain.data / "orders.csv").write_text("order_id\n1\n2\n")          # schema drift: column vanished
    assert domain.run_check("orders") == "customer_id|not_null|missing_column"
