import json

import pytest
from conftest import FakeClient, resp, text, tool_use

from API.harness import caching, loop, memory
from API.harness.compaction import maybe_compact
from API.harness.history import History
from API.harness.tokens import Meter


def run(client, domain, hist, user, meter=None):
    meter = meter or Meter()
    return loop.run_turn(client, "claude-opus-5-5", hist, domain, meter, user), meter


def test_parallel_tool_results_in_one_message(domain, tmp_path):
    c = FakeClient([resp([tool_use(1, "recall", query="x"), tool_use(2, "list_rules")], "tool_use"),
                    resp([text("done")], "end_turn")])
    result, _ = run(c, domain, History(tmp_path / "h.jsonl"), "hi")
    assert result.text == "done" and result.tools_used == ["recall", "list_rules"]
    last_user = c.calls[1]["messages"][-1]
    assert last_user["role"] == "user" and [b["tool_use_id"] for b in last_user["content"]] == ["tu1", "tu2"]


def test_tool_error_returns_is_error_and_loop_continues(domain, tmp_path):
    c = FakeClient([resp([tool_use(1, "profile_table", table="../x")], "tool_use"), resp([text("sorry")], "end_turn")])
    result, _ = run(c, domain, History(tmp_path / "h.jsonl"), "hi")
    assert c.calls[1]["messages"][-1]["content"][0]["is_error"] is True and result.text == "sorry"


def test_crashing_tool_does_not_kill_loop(domain, tmp_path, monkeypatch):
    monkeypatch.setattr(type(domain), "recall", lambda self, query="": 1 / 0)
    c = FakeClient([resp([tool_use(1, "recall")], "tool_use"), resp([text("ok")], "end_turn")])
    result, _ = run(c, domain, History(tmp_path / "h.jsonl"), "hi")
    assert c.calls[1]["messages"][-1]["content"][0]["is_error"] is True and result.stop_reason == "end_turn"


def test_cache_breakpoints_sent_but_not_stored(domain, tmp_path):
    c = FakeClient([resp([text("ok")], "end_turn")])
    hist = History(tmp_path / "h.jsonl")
    run(c, domain, hist, "hi")
    req = c.calls[0]
    assert req["tools"][-1]["cache_control"] and req["system"][-1]["cache_control"]
    assert req["messages"][-1]["content"][-1]["cache_control"]
    assert "cache_control" not in str(hist.records)
    assert req["output_config"] == {"effort": "medium"} and req["model"] == "claude-opus-5-5"


def test_caching_apply_does_not_mutate_inputs():
    tools, system, messages = [{"name": "a"}], [{"type": "text", "text": "s"}], [{"role": "user", "content": "plain"}]
    caching.apply(tools, system, messages)
    assert "cache_control" not in tools[0] and "cache_control" not in system[0] and messages[0]["content"] == "plain"


def test_history_is_append_only_across_instances(domain, tmp_path):
    p = tmp_path / "h.jsonl"
    run(FakeClient([resp([text("a")], "end_turn")]), domain, History(p), "one")
    before = p.read_text().splitlines()
    run(FakeClient([resp([text("b")], "end_turn")]), domain, History(p), "two")
    after = p.read_text().splitlines()
    assert after[:len(before)] == before and len(after) > len(before)


def test_thinking_blocks_are_stored_verbatim(domain, tmp_path):
    thinking = {"type": "thinking", "thinking": "", "signature": "sig"}
    blocks = [type(text("x"))(**thinking), text("answer")]
    c = FakeClient([resp(blocks, "end_turn")])
    hist = History(tmp_path / "h.jsonl")
    run(c, domain, hist, "hi")
    assert hist.messages()[-1]["content"][0] == thinking


def test_context_injects_only_relevant_facts(domain, tmp_path):
    domain.remember("orders_owner", "Dana")
    domain.remember("favorite_color", "blue")
    c = FakeClient([resp([text("ok")], "end_turn")])
    run(c, domain, History(tmp_path / "h.jsonl"), "who owns orders?")
    sent = c.calls[0]["messages"][0]["content"][0]["text"]
    assert "orders_owner=Dana" in sent and "blue" not in sent


def test_memory_matches_whole_words_with_underscore_keys(domain):
    domain.remember("severity_threshold", "high")
    assert memory.relevant_facts(domain, "set my severity_threshold to medium") == ["severity_threshold=high"]
    domain.remember("other_thing", "x")
    assert memory.relevant_facts(domain, "the") == []           # stopword; "the" no longer matches inside "other"


def test_token_meter_accumulates_and_costs(domain, tmp_path):
    c = FakeClient([resp([tool_use(1, "list_rules")], "tool_use", inp=1000, out=100, cr=0, cw=500),
                    resp([text("x")], "end_turn", inp=50, out=20, cr=1500, cw=0)])
    _, meter = run(c, domain, History(tmp_path / "h.jsonl"), "hi")
    t = meter.turns[0]
    assert (t["input"], t["cache_read"], t["cache_write"], t["output"], t["calls"]) == (1050, 1500, 500, 120, 2)
    assert t["cost_usd"] == pytest.approx((1050 * 4 + 120 * 20 + 1500 * 0.2 + 500 * 5) / 1e6)


def test_step_limit_raises_and_history_stays_valid(domain, tmp_path, monkeypatch):
    monkeypatch.setattr(loop, "MAX_STEPS", 2)
    c = FakeClient([resp([tool_use(i, "list_rules")], "tool_use") for i in range(2)])
    hist = History(tmp_path / "h.jsonl")
    with pytest.raises(loop.StepLimitExceeded):
        run(c, domain, hist, "loop forever")
    roles = [m["role"] for m in hist.messages()]
    assert all(a != b for a, b in zip(roles, roles[1:], strict=False)) and roles[-1] == "assistant"


def test_max_tokens_mid_tool_call_answers_the_dangling_tool_use(domain, tmp_path):
    c = FakeClient([resp([tool_use(1, "list_rules")], "max_tokens")])
    hist = History(tmp_path / "h.jsonl")
    result, _ = run(c, domain, hist, "hi")
    assert result.stop_reason == "max_tokens"
    answered = hist.messages()[-1]["content"][0]
    assert answered["tool_use_id"] == "tu1" and answered["is_error"] is True


def test_api_error_keeps_history_sendable_and_meter_closed(domain, tmp_path):
    hist = History(tmp_path / "h.jsonl")
    meter = Meter()
    with pytest.raises(RuntimeError, match="boom"):
        run(FakeClient([RuntimeError("boom")]), domain, hist, "hi", meter)
    assert [m["role"] for m in hist.messages()] == ["user", "assistant"] and len(meter.turns) == 1
    run(FakeClient([resp([text("recovered")], "end_turn")]), domain, hist, "again", meter)


def test_compaction_sends_tools_meters_usage_and_only_appends(domain, tmp_path):
    hist = History(tmp_path / "h.jsonl")
    hist.append({"role": "user", "content": "old"})
    hist.append({"role": "assistant", "content": [{"type": "text", "text": "old reply"}]})
    meter = Meter()
    meter.start()
    meter.add(resp([], "end_turn", inp=50_000).usage)
    meter.finish()
    meter.start()
    c = FakeClient([resp([text("SUMMARY")], "end_turn", inp=777)])
    assert maybe_compact(c, "m", hist, meter, [{"name": "t"}], [{"type": "text", "text": "s"}]) is True
    req = c.calls[0]
    assert req["tools"] and req["tool_choice"] == {"type": "none"}
    assert meter.cur["input"] == 777 and meter.cur["calls"] == 1
    assert "SUMMARY" in hist.messages()[0]["content"] and len(hist.messages()) == 1
    assert len(hist.records) == 3
    meter.finish()
    assert maybe_compact(c, "m", hist, meter, [], []) is False   # small last prompt: no second compaction


def test_agent_history_ok_detects_rewritten_history(domain, tmp_path):
    from API.agent import APIAgent
    state = tmp_path / "st"
    (state / "data").mkdir(parents=True)
    first = APIAgent(state, FakeClient([resp([text("a")], "end_turn")]))
    first.turn("one")
    marker = first.close()
    second = APIAgent(state, FakeClient([resp([text("b")], "end_turn")]))
    assert second.history_ok(marker) is False                    # nothing appended yet
    second.turn("two")
    assert second.history_ok(marker) is True
    lines = (state / "history.jsonl").read_text().splitlines()
    lines[0] = json.dumps({"msg": {"role": "user", "content": "tampered"}})
    (state / "history.jsonl").write_text("\n".join(lines) + "\n")
    assert APIAgent(state, FakeClient([])).history_ok(marker) is False
