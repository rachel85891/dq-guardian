import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from shared.domain import Domain

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def domain(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "orders.csv").write_text((ROOT / "data" / "orders.csv").read_text("utf-8"), "utf-8")
    return Domain(tmp_path, tmp_path / "data")


class Block:
    """Minimal stand-in for an SDK content block."""

    def __init__(self, **fields):
        self.fields = fields
        self.__dict__.update(fields)

    def model_dump(self, **_):
        return dict(self.fields)


def text(t):
    return Block(type="text", text=t)


def tool_use(i, name, **inp):
    return Block(type="tool_use", id=f"tu{i}", name=name, input=inp)


def resp(blocks, stop, inp=100, out=10, cr=0, cw=0):
    usage = SimpleNamespace(input_tokens=inp, output_tokens=out, cache_read_input_tokens=cr, cache_creation_input_tokens=cw)
    return SimpleNamespace(content=blocks, stop_reason=stop, usage=usage)


class FakeClient:
    """Scripted stand-in for anthropic.Anthropic: records every request, replays canned responses or raises."""

    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
