import argparse
from pathlib import Path

from API.agent import APIAgent
from shared.runner import loc, run


def count_lines() -> dict[str, int]:
    harness = Path(__file__).parent / "harness"
    return {p.stem: loc(p) for p in sorted(harness.glob("*.py")) if p.stem != "__init__"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="scenario.json")
    parser.add_argument("--out", default="results/api.json")
    args = parser.parse_args()
    run(APIAgent, args.scenario, args.out, "api", count_lines)
