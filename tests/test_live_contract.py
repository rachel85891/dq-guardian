"""Contract checks against the real API. Skipped unless ANTHROPIC_API_KEY is set (costs a few cents)."""
import os

import pytest

from API.harness import caching, context, tools
from shared.config import EFFORT, MODEL

pytestmark = [pytest.mark.live, pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="no API key")]


@pytest.fixture(scope="module")
def client():
    import anthropic
    return anthropic.Anthropic()


def test_request_shape_with_effort_cache_control_and_tools_is_accepted(client):
    schemas, system, messages = caching.apply(tools.SCHEMAS, context.SYSTEM, [{"role": "user", "content": "say hi"}])
    r = client.messages.create(model=MODEL, max_tokens=64, tools=schemas, system=system, messages=messages,
                               output_config={"effort": EFFORT})
    assert r.usage.output_tokens > 0


def test_history_with_tool_blocks_needs_tools_for_the_compaction_request(client):
    history = [
        {"role": "user", "content": "list rules"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_1", "name": "list_rules", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "none"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "No rules."}]},
        {"role": "user", "content": "Summarize this conversation briefly. Do not call tools."},
    ]
    r = client.messages.create(model=MODEL, max_tokens=200, system=context.SYSTEM, tools=tools.SCHEMAS,
                               tool_choice={"type": "none"}, messages=history)
    assert r.stop_reason == "end_turn"
