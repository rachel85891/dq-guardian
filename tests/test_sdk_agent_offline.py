"""SDKAgent logic with Claude Code replaced by a fake client: usage parsing, call counting, memory file, errors."""
import pytest

import SDK.agent as sdk_agent
from claude_agent_sdk import AssistantMessage, ResultMessage, ToolUseBlock


def assistant(message_id, *tool_names):
    blocks = [ToolUseBlock(id=f"t{i}", name=f"mcp__dq__{n}", input={}) for i, n in enumerate(tool_names)]
    return AssistantMessage(content=blocks, model="m", message_id=message_id)


def result(**over):
    base = dict(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=3, session_id="S1",
                result="Owner is Dana", total_cost_usd=0.01, stop_reason="end_turn",
                usage={"input_tokens": 5, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 20, "output_tokens": 7})
    return ResultMessage(**{**base, **over})


class FakeSDKClient:
    script: list = []

    def __init__(self, options):
        self.options, self.queries, self.connected = options, [], False

    async def connect(self):
        self.connected = True

    async def disconnect(self):
        self.connected = False

    async def query(self, text):
        self.queries.append(text)

    async def receive_response(self):
        for message in self.script:
            yield message


@pytest.fixture
def agent(tmp_path, monkeypatch):
    monkeypatch.setattr(sdk_agent, "ClaudeSDKClient", FakeSDKClient)
    (tmp_path / "data").mkdir()
    return sdk_agent.SDKAgent(tmp_path)


def test_options_are_locked_down(agent):
    o = agent.client.options
    assert o.strict_mcp_config is True and o.tools == [] and o.setting_sources == ["project"]
    assert o.allowed_tools and all(t.startswith("mcp__dq__") for t in o.allowed_tools) and o.system_prompt


def test_turn_parses_usage_dedupes_model_calls_and_writes_memory(agent):
    agent.domain.remember("orders_owner", "Dana")
    FakeSDKClient.script = [assistant("m1", "recall"), assistant("m1", "list_rules"), assistant("m2"), result()]
    out = agent.turn("who owns orders?")
    assert out["tools"] == ["recall", "list_rules"] and out["calls"] == 2          # two blocks of m1 = ONE model call
    assert (out["input"], out["cache_read"], out["cache_write"], out["output"]) == (5, 100, 20, 7)
    assert out["cost_usd"] == 0.01 and out["text"] == "Owner is Dana"
    assert "orders_owner=Dana" in (agent.state / "CLAUDE.md").read_text("utf-8")
    assert (agent.state / "session_id.txt").read_text() == "S1"


def test_error_result_raises(agent):
    FakeSDKClient.script = [result(is_error=True, subtype="error_during_execution", errors=["x"])]
    with pytest.raises(RuntimeError, match="SDK turn failed"):
        agent.turn("hi")


def test_missing_result_raises(agent):
    FakeSDKClient.script = [assistant("m1")]
    with pytest.raises(RuntimeError, match="without a ResultMessage"):
        agent.turn("hi")


def test_new_instance_resumes_same_session(agent, tmp_path):
    FakeSDKClient.script = [result()]
    agent.turn("one")
    marker = agent.close()
    second = sdk_agent.SDKAgent(tmp_path)
    assert second.client.options.resume == "S1"
    FakeSDKClient.script = [result()]
    second.turn("two")
    assert second.history_ok(marker) is True
    assert second.history_ok("other") is False
