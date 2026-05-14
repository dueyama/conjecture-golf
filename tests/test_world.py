import pytest

from conjecture_golf.world import ValidationError, count_relation, evolve, related_coords, validate_board


def test_validate_board_accepts_5x5():
    board = [".W...", ".....", "..F..", ".....", "....."]
    assert validate_board(board) == board


def test_validate_board_rejects_bad_symbol():
    with pytest.raises(ValidationError):
        validate_board([".....", ".X...", "..F..", ".....", "....."])


def test_related_coords_center_has_4_orthogonal():
    assert set(related_coords(2, 2, "orthogonal")) == {(1, 2), (3, 2), (2, 1), (2, 3)}


def test_evolve_flower_growth():
    board = [".W...", ".....", "..F..", ".....", "....."]
    after = evolve(board)
    assert after[1][2] == "F"


def test_stone_blocks_flower_growth():
    board = [".W...", ".....", ".SF..", ".....", "....."]
    after = evolve(board)
    assert after[1][2] == "."


def test_water_evaporates_when_trapped():
    board = ["FFFFF", "FSSSF", "FSWSF", "FSSSF", "FFFFF"]
    assert evolve(board)[2][2] == "."
