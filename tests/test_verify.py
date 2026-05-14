from conjecture_golf.verify import check_counterexample, verify_conjecture

TRUE_CONJECTURE = {
    "player": "blue",
    "name": "growth_true",
    "if": [
        {"target_is": "."},
        {"exists": {"symbol": "W", "relation": "diagonal"}},
        {"exists": {"symbol": "F", "relation": "orthogonal"}},
        {"not_exists": {"symbol": "S", "relation": "king"}},
    ],
    "then": {"target_becomes": "F"},
}

FALSE_CONJECTURE = {
    "player": "red",
    "name": "growth_too_broad",
    "if": [
        {"target_is": "."},
        {"exists": {"symbol": "W", "relation": "diagonal"}},
        {"exists": {"symbol": "F", "relation": "orthogonal"}},
    ],
    "then": {"target_becomes": "F"},
}


def test_true_conjecture_holds_exhaustive_local():
    verdict = verify_conjecture(TRUE_CONJECTURE)
    assert verdict.ok
    assert verdict.details["coverage"] > 0


def test_false_conjecture_is_refuted():
    verdict = verify_conjecture(FALSE_CONJECTURE)
    assert not verdict.ok
    assert verdict.details["counterexample"]


def test_counterexample_valid_against_false_conjecture():
    board = [".W...", ".....", ".SF..", ".....", "....."]
    verdict = check_counterexample(FALSE_CONJECTURE, board)
    assert verdict.ok
    assert verdict.details["actual"] == "."


def test_counterexample_invalid_against_true_conjecture():
    board = [".W...", ".....", "..F..", ".....", "....."]
    verdict = check_counterexample(TRUE_CONJECTURE, board)
    assert not verdict.ok
