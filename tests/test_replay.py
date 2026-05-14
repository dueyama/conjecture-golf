from conjecture_golf.replay import apply_command, replay_file, replay_records, ReplayState
from conjecture_golf.score import leaderboard_rows


def test_replay_basic_transcript_is_deterministic():
    a = replay_file("examples/transcripts/basic.jsonl")
    b = replay_file("examples/transcripts/basic.jsonl")
    assert [v.to_dict() for v in a.verdicts] == [v.to_dict() for v in b.verdicts]


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
