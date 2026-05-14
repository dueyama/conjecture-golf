from conjecture_golf.canonical import canonical_3x3, local_3x3_from_board, witness_id


def test_canonical_3x3_treats_rotations_as_same():
    pattern = ("..W", ".F.", "S..")
    rotated = ("S..", ".F.", "..W")

    assert canonical_3x3(pattern) == canonical_3x3(rotated)


def test_local_3x3_pads_board_edges():
    board = [".....", ".S...", ".....", ".....", "....."]

    assert local_3x3_from_board(board, 0, 0) == ("###", "#..", "#.S")


def test_witness_id_includes_outcome_and_canonical_pattern():
    board = [".....", ".....", ".....", ".SFW.", "....."]

    first = witness_id(board, [2, 2], expected="F", actual=".")
    second = witness_id(board, [2, 2], expected="F", actual=".")

    assert first == second
    assert first.startswith("expected=F:actual=.:pattern=")
