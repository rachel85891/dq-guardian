import argparse
import os
import re
import sys
from collections import Counter
from pathlib import Path

from SDK.agent import SDKAgent
from shared.runner import loc, run

_MARKER = re.compile(r"# replaces: harness/(\w+)\.py")


def count_lines() -> dict[str, int]:
    """Lines per replaced harness part = lines carrying its `# replaces:` marker; `config_total` = all SDK code."""
    here = Path(__file__).parent
    per_part: Counter[str] = Counter()
    for path in here.glob("*.py"):
        for line in path.read_text("utf-8").splitlines():
            match = _MARKER.search(line)
            if match:
                per_part[match.group(1)] += 1
    return {**dict(per_part), "config_total": sum(loc(p) for p in here.glob("*.py") if p.stem != "__init__")}


if __name__ == "__main__":
    if os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is set: the SDK run would bill that key instead of your Claude Code login. Unset it.")
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="scenario.json")
    parser.add_argument("--out", default="results/sdk.json")
    args = parser.parse_args()
    run(SDKAgent, args.scenario, args.out, "sdk", count_lines)
