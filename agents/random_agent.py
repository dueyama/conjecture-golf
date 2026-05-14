"""Tiny baseline agent that emits a random-looking valid command.

This agent intentionally does not use external AI. It is only a seed for future
Codex work.
"""

from __future__ import annotations

import json
import random

SYMBOLS = [".", "F", "W", "S"]
RELATIONS = ["orthogonal", "diagonal", "king"]


def make_conjecture(player: str = "random-agent", seed: int | None = None) -> dict:
    rng = random.Random(seed)
    target = rng.choice(SYMBOLS)
    neighbor = rng.choice(SYMBOLS)
    relation = rng.choice(RELATIONS)
    result = rng.choice(SYMBOLS)
    return {
        "type": "conjecture",
        "player": player,
        "name": f"random_{target}_{neighbor}_{relation}_{result}_{seed if seed is not None else 'x'}".replace(".", "empty"),
        "if": [
            {"target_is": target},
            {"exists": {"symbol": neighbor, "relation": relation}},
        ],
        "then": {"target_becomes": result},
    }


def main() -> int:
    print(json.dumps(make_conjecture(seed=0), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
