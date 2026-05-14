from conjecture_golf.verify import check_counterexample, redact_verdict, verify_conjecture

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

STONE_EQUIVALENCE = {
    "player": "stone",
    "name": "stone_stays_stone_exactly",
    "claim_kind": "equivalence",
    "if": [{"target_is": "S"}],
    "then": {"target_becomes": "S"},
}

FALSE_NECESSARY = {
    "player": "stone",
    "name": "stone_needs_empty_before",
    "claim_kind": "necessary",
    "if": [{"target_is": "."}],
    "then": {"target_becomes": "S"},
}


def test_true_conjecture_holds_exhaustive_local():
    verdict = verify_conjecture(TRUE_CONJECTURE)
    assert verdict.ok
    assert verdict.details["coverage"] > 0


def test_false_conjecture_is_refuted():
    verdict = verify_conjecture(FALSE_CONJECTURE)
    assert not verdict.ok
    assert verdict.details["counterexample"]


def test_redacted_reveal_policy_hides_false_conjecture_witness_board():
    verdict = verify_conjecture(FALSE_CONJECTURE)
    redacted = redact_verdict(verdict, reveal_policy="redacted")

    assert "counterexample" not in redacted.details
    assert redacted.details["counterexample_redacted"] is True
    assert redacted.details["counterexample_digest"]
    assert redacted.details["counterexample_summary"]["expected"] == "F"


def test_counterexample_valid_against_false_conjecture():
    board = [".W...", ".....", ".SF..", ".....", "....."]
    verdict = check_counterexample(FALSE_CONJECTURE, board)
    assert verdict.ok
    assert verdict.details["actual"] == "."


def test_counterexample_invalid_against_true_conjecture():
    board = [".W...", ".....", "..F..", ".....", "....."]
    verdict = check_counterexample(TRUE_CONJECTURE, board)
    assert not verdict.ok


def test_equivalence_claim_can_hold():
    verdict = verify_conjecture(STONE_EQUIVALENCE)

    assert verdict.ok
    assert verdict.details["claim_kind"] == "equivalence"
    assert verdict.details["coverage"] > 0


def test_necessary_claim_can_be_refuted():
    verdict = verify_conjecture(FALSE_NECESSARY)

    assert not verdict.ok
    assert verdict.details["claim_kind"] == "necessary"
    assert verdict.details["counterexample"]["antecedent"] is False


def test_counterexample_valid_against_false_necessary_claim():
    board = [".....", ".....", "..S..", ".....", "....."]
    verdict = check_counterexample(FALSE_NECESSARY, board)

    assert verdict.ok
    assert verdict.details["actual"] == "S"
