import json
from pathlib import Path

from conjecture_golf.season_engine import compile_season
from conjecture_golf.season_spec import compile_season_spec, load_season_spec
from conjecture_golf.world import canonical_test_boards, evolve


def _base_spec():
    return json.loads(Path("seasons/season_0.json").read_text(encoding="utf-8"))


def test_season_engine_is_deterministic_and_does_not_mutate_input():
    engine = compile_season(load_season_spec("seasons/season_0.json"))
    board = [".W...", ".....", "..F..", ".....", "....."]
    before = list(board)

    first = engine.step_board(board)
    second = engine.step_board(board)

    assert first == second
    assert board == before


def test_priority_uses_lower_number_first():
    spec_data = _base_spec()
    spec_data["transition"]["rules"] = [
        {
            "id": "first",
            "priority": 1,
            "when": [{"target_is": "."}],
            "becomes": "F",
        },
        {
            "id": "second",
            "priority": 2,
            "when": [{"target_is": "."}],
            "becomes": "W",
        },
    ]
    spec = compile_season_spec(spec_data)
    engine = compile_season(spec)

    assert engine.next_symbol_for_cell([".....", ".....", ".....", ".....", "....."], 2, 2) == "F"


def test_season0_spec_matches_world_on_representative_boards():
    engine = compile_season(load_season_spec("seasons/season_0.json"))

    for board in canonical_test_boards():
        assert engine.step_board(board) == evolve(board)
