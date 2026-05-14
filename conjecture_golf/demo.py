"""Readable demo for Conjecture Golf."""

from __future__ import annotations

import json

from .replay import replay_file
from .score import leaderboard_rows, render_markdown
from .verify import verify_file
from .world import canonical_test_boards, evolve, format_board


def main() -> int:
    print("Conjecture Golf demo")
    print("====================")
    print()
    board = canonical_test_boards()[0]
    print("A public 5x5 world evolves deterministically.")
    print("Before:")
    print(format_board(board))
    print("After:")
    print(format_board(evolve(board)))
    print()

    print("Verifying a sample conjecture:")
    verdict = verify_file("examples/conjectures/growth_true.json")
    print(json.dumps(verdict.to_dict(), ensure_ascii=False, indent=2))
    print()

    print("Replaying a transcript:")
    state = replay_file("examples/transcripts/basic.jsonl")
    print(render_markdown(leaderboard_rows(state.scores)))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
