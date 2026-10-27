import asyncio
import os
import subprocess
import sys

from conftest import ROOT

from SDK import tools as sdk_tools
from SDK.main import count_lines
from shared import domain as D


def call(handler, args):
    return asyncio.run(handler.handler(args))


def test_sdk_exposes_all_tools(domain):
    assert len(sdk_tools.ALLOWED) == len(D.SPECS) == 8
    assert all(a.startswith("mcp__dq__") for a in sdk_tools.ALLOWED)
    assert sdk_tools.build_server(domain)["name"] == "dq"


def test_sdk_tool_success_and_is_error(domain):
    tool = sdk_tools.make_tool(domain, D.SPECS["profile_table"])
    ok = call(tool, {"table": "orders"})
    assert "is_error" not in ok and ok["content"][0]["text"].startswith("rows=6")
    bad = call(tool, {"table": "../etc"})
    assert bad["is_error"] is True


def test_sdk_tool_survives_a_crash(domain, monkeypatch):
    monkeypatch.setattr(type(domain), "recall", lambda self, query="": 1 / 0)
    out = call(sdk_tools.make_tool(domain, D.SPECS["recall"]), {})
    assert out["is_error"] is True and "internal error" in out["content"][0]["text"]


def test_every_replaced_harness_part_is_marked():
    counts = count_lines()
    for part in ("loop", "tools", "history", "memory", "tokens", "context"):
        assert counts.get(part, 0) >= 1, part
    assert counts["config_total"] > 0
    assert "strict_mcp_config=True" in (ROOT / "SDK" / "agent.py").read_text("utf-8")


def test_sdk_refuses_to_run_with_api_key():
    env = dict(os.environ, ANTHROPIC_API_KEY="x")
    r = subprocess.run([sys.executable, str(ROOT / "SDK" / "main.py")], env=env, capture_output=True, text=True)
    assert r.returncode != 0 and "ANTHROPIC_API_KEY" in r.stderr + r.stdout


def test_api_main_help_imports_cleanly():
    r = subprocess.run([sys.executable, str(ROOT / "API" / "main.py"), "--help"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_loc_ignores_docstrings_and_comments(tmp_path):
    from shared.runner import loc
    f = tmp_path / "m.py"
    f.write_text('"""module doc\nmore doc\n"""\n# comment\n\ndef f():\n    """doc\n    line"""\n    return 1\n')
    assert loc(f) == 2
