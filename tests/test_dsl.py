import pytest

from conjecture_golf.dsl import antecedent_matches, complexity, validate_conjecture
from conjecture_golf.world import ValidationError

TRUE_CONJECTURE = {
    "name": "growth",
    "if": [
        {"target_is": "."},
        {"exists": {"symbol": "W", "relation": "diagonal"}},
        {"exists": {"symbol": "F", "relation": "orthogonal"}},
        {"not_exists": {"symbol": "S", "relation": "king"}},
    ],
    "then": {"target_becomes": "F"},
}


def test_validate_conjecture_normalizes():
    assert validate_conjecture(TRUE_CONJECTURE)["name"] == "growth"


def test_validate_conjecture_rejects_unknown_field():
    bad = dict(TRUE_CONJECTURE)
    bad["surprise"] = True
    with pytest.raises(ValidationError):
        validate_conjecture(bad)


def test_antecedent_matches_expected_cell():
    board = [".W...", ".....", "..F..", ".....", "....."]
    assert antecedent_matches(TRUE_CONJECTURE, board, 1, 2)


def test_antecedent_blocked_by_stone():
    board = [".W...", ".....", ".SF..", ".....", "....."]
    assert not antecedent_matches(TRUE_CONJECTURE, board, 1, 2)


def test_complexity_is_deterministic():
    assert complexity(TRUE_CONJECTURE) == complexity(TRUE_CONJECTURE)
    assert complexity(TRUE_CONJECTURE) > 0
