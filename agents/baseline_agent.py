"""Baseline agent that emits known useful conjectures from the public world."""

from __future__ import annotations

import json


def flower_growth_conjecture(player: str = "baseline-agent") -> dict:
    return {
        "type": "conjecture",
        "player": player,
        "name": "baseline_flower_growth",
        "if": [
            {"target_is": "."},
            {"exists": {"symbol": "W", "relation": "diagonal"}},
            {"exists": {"symbol": "F", "relation": "orthogonal"}},
            {"not_exists": {"symbol": "S", "relation": "king"}},
        ],
        "then": {"target_becomes": "F"},
    }


def trapped_water_conjecture(player: str = "baseline-agent") -> dict:
    return {
        "type": "conjecture",
        "player": player,
        "name": "baseline_trapped_water_evaporates",
        "if": [
            {"target_is": "W"},
            {"not_exists": {"symbol": ".", "relation": "orthogonal"}},
        ],
        "then": {"target_becomes": "."},
    }


def main() -> int:
    for command in [flower_growth_conjecture(), trapped_water_conjecture()]:
        print(json.dumps(command, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
