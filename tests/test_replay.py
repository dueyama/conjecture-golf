from conjecture_golf.replay import apply_command, replay_file, replay_records, ReplayState
from conjecture_golf.score import leaderboard_rows
from conjecture_golf.season_engine import load_compiled_season


TRUE_FLOWER = {
    "type": "conjecture",
    "player": "blue",
    "name": "flower_growth",
    "if": [
        {"target_is": "."},
        {"exists": {"symbol": "W", "relation": "diagonal"}},
        {"exists": {"symbol": "F", "relation": "orthogonal"}},
        {"not_exists": {"symbol": "S", "relation": "king"}},
    ],
    "then": {"target_becomes": "F"},
}

STONE_EQUIVALENCE = {
    "type": "conjecture",
    "player": "stone",
    "name": "stone_stays_stone_exactly",
    "claim_kind": "equivalence",
    "if": [{"target_is": "S"}],
    "then": {"target_becomes": "S"},
}


def test_replay_basic_transcript_is_deterministic():
    a = replay_file("examples/transcripts/basic.jsonl")
    b = replay_file("examples/transcripts/basic.jsonl")
    assert [v.to_dict() for v in a.verdicts] == [v.to_dict() for v in b.verdicts]


def test_replay_basic_transcript_with_season_spec_matches_default_scores():
    season = load_compiled_season("seasons/season_0.json")
    default = replay_file("examples/transcripts/basic.jsonl", season_scoring=True)
    explicit = replay_file("examples/transcripts/basic.jsonl", season_scoring=True, season=season)

    assert leaderboard_rows(default.scores) == leaderboard_rows(explicit.scores)


def test_counterexample_can_target_prior_false_conjecture():
    records = [
        {"type": "conjecture", "player": "red", "name": "too_broad", "if": [{"target_is": "."}, {"exists": {"symbol": "W", "relation": "diagonal"}}, {"exists": {"symbol": "F", "relation": "orthogonal"}}], "then": {"target_becomes": "F"}},
        {"type": "counterexample", "player": "green", "against": "too_broad", "before": [".W...", ".....", ".SF..", ".....", "....."]},
    ]
    state = replay_records(records)
    rows = leaderboard_rows(state.scores)
    assert rows[0]["player"] == "green"
    assert rows[0]["valid_counterexamples"] == 1


def test_invalid_command_penalty():
    state = ReplayState()
    verdict = apply_command(state, {"type": "counterexample", "player": "bad", "against": "missing", "before": ["....."]})
    assert not verdict.ok
    assert state.scores["bad"].invalid_moves == 1


def test_player_cooldown_rejects_fast_repeat_commands():
    records = [
        {"type": "score", "player": "fast", "_meta": {"created_at": "2026-05-14T00:00:00Z"}},
        {"type": "score", "player": "fast", "_meta": {"created_at": "2026-05-14T00:30:00Z"}},
    ]

    state = replay_records(records, min_player_interval_seconds=3600)

    assert state.verdicts[0].ok
    assert not state.verdicts[1].ok
    assert state.verdicts[1].details["reason"] == "player_cooldown"
    assert state.scores["fast"].invalid_moves == 1


def test_player_cooldown_allows_different_players():
    records = [
        {"type": "score", "player": "one", "_meta": {"created_at": "2026-05-14T00:00:00Z"}},
        {"type": "score", "player": "two", "_meta": {"created_at": "2026-05-14T00:01:00Z"}},
    ]

    state = replay_records(records, min_player_interval_seconds=3600)

    assert all(verdict.ok for verdict in state.verdicts)


def test_player_cooldown_uses_issue_author_when_present():
    records = [
        {
            "type": "score",
            "player": "declared-one",
            "_meta": {"created_at": "2026-05-14T00:00:00Z", "author_login": "same-gh-user"},
        },
        {
            "type": "score",
            "player": "declared-two",
            "_meta": {"created_at": "2026-05-14T00:30:00Z", "author_login": "same-gh-user"},
        },
    ]

    state = replay_records(records, min_player_interval_seconds=3600)

    assert state.verdicts[0].ok
    assert not state.verdicts[1].ok
    assert state.verdicts[1].details["cooldown_identity"] == "same-gh-user"


def test_season_scoring_rejects_duplicate_conjecture():
    duplicate = {**TRUE_FLOWER, "player": "green", "name": "same_rule_new_name"}

    state = replay_records([TRUE_FLOWER, duplicate], season_scoring=True)

    assert state.verdicts[0].ok
    assert state.verdicts[0].details["season_new_obligations"] > 0
    assert not state.verdicts[1].ok
    assert state.verdicts[1].details["reason"] == "duplicate_conjecture"
    assert state.verdicts[1].details["score_components"]["duplicate_conjecture_penalty"] == -2


def test_season_scoring_diagnostics_split_equivalence_sides():
    state = replay_records([STONE_EQUIVALENCE], season_scoring=True)

    components = state.verdicts[0].details["score_components"]
    assert components["new_sufficient_obligations"] > 0
    assert components["new_necessary_obligations"] > 0
    assert state.verdicts[0].details["season_total_obligation_counts"]["necessary"] > 0


def test_season_scoring_gives_no_points_for_stale_true_specialization():
    stale_specialization = {
        **TRUE_FLOWER,
        "player": "green",
        "name": "flower_growth_redundant",
        "if": [
            *TRUE_FLOWER["if"],
            {"count_at_least": {"symbol": "W", "relation": "diagonal", "n": 1}},
        ],
    }

    state = replay_records([TRUE_FLOWER, stale_specialization], season_scoring=True)

    assert state.verdicts[1].ok
    assert state.verdicts[1].score_delta == 0
    assert state.verdicts[1].details["season_score_basis"] == "stale_true_conjecture"


def test_season_scoring_discounts_verifier_revealed_counterexample():
    records = [
        {
            "type": "conjecture",
            "player": "red",
            "name": "too_broad",
            "if": [
                {"target_is": "."},
                {"exists": {"symbol": "W", "relation": "diagonal"}},
                {"exists": {"symbol": "F", "relation": "orthogonal"}},
            ],
            "then": {"target_becomes": "F"},
        },
        {
            "type": "counterexample",
            "player": "green",
            "against": "too_broad",
            "before": [".....", ".....", ".....", ".SFW.", "....."],
        },
    ]

    state = replay_records(records, season_scoring=True)

    assert state.verdicts[1].ok
    assert state.verdicts[1].score_delta == 5
    assert state.verdicts[1].details["season_score_basis"] == "verifier_revealed_counterexample"
    assert state.verdicts[1].details["score_components"]["verifier_revealed_penalty"] == 10
    assert state.verdicts[1].details["score_components"]["target_value_observed"] > 0


def test_season_scoring_penalizes_duplicate_witness_patterns_across_targets():
    false_conjecture = {
        "type": "conjecture",
        "player": "red",
        "name": "too_broad",
        "if": [
            {"target_is": "."},
            {"exists": {"symbol": "W", "relation": "diagonal"}},
            {"exists": {"symbol": "F", "relation": "orthogonal"}},
        ],
        "then": {"target_becomes": "F"},
    }
    duplicate_false_conjecture = {**false_conjecture, "name": "too_broad_again", "player": "orange"}
    witness = [".....", ".....", ".....", ".SFW.", "....."]
    records = [
        false_conjecture,
        {"type": "counterexample", "player": "green", "against": "too_broad", "before": witness},
        duplicate_false_conjecture,
        {"type": "counterexample", "player": "green", "against": "too_broad_again", "before": witness},
    ]

    state = replay_records(records, season_scoring=True)

    assert state.verdicts[1].details["season_score_basis"] == "verifier_revealed_counterexample"
    assert state.verdicts[3].score_delta == 2
    assert state.verdicts[3].details["season_score_basis"] == "duplicate_witness"
