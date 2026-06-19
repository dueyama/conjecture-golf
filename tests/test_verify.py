from conjecture_golf.verify import check_counterexample, redact_verdict, verify_conjecture
from conjecture_golf.season_engine import load_compiled_season

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

TRIVIAL_COUNT_NECESSARY = {
    "player": "stone",
    "name": "trivial_count_necessary",
    "claim_kind": "necessary",
    "if": [{"count_at_least": {"symbol": "S", "relation": "king", "n": 0}}],
    "then": {"target_becomes": "W"},
}


def test_true_conjecture_holds_exhaustive_local():
    verdict = verify_conjecture(TRUE_CONJECTURE)
    assert verdict.ok
    assert verdict.details["coverage"] > 0


def test_true_conjecture_holds_with_season_spec():
    season = load_compiled_season("seasons/season_0.json")
    verdict = verify_conjecture(TRUE_CONJECTURE, season=season)

    assert verdict.ok
    assert verdict.details["season_id"] == "season_0"
    assert verdict.details["coverage"] == 4225


def test_season_1_rejects_count_at_least_zero_conjecture_guard():
    season = load_compiled_season("seasons/season_1.json")
    verdict = verify_conjecture(TRIVIAL_COUNT_NECESSARY, season=season)

    assert not verdict.ok
    assert "count_at_least with n=0" in verdict.message


def test_season_0_allows_count_at_least_zero_for_archive_replay():
    season = load_compiled_season("seasons/season_0.json")
    verdict = verify_conjecture(TRIVIAL_COUNT_NECESSARY, season=season)

    assert verdict.ok


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


def test_counterexample_valid_with_season_spec():
    season = load_compiled_season("seasons/season_0.json")
    board = [".W...", ".....", ".SF..", ".....", "....."]
    verdict = check_counterexample(FALSE_CONJECTURE, board, season=season)

    assert verdict.ok
    assert verdict.details["season_id"] == "season_0"


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
