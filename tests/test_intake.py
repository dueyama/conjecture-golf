import json

from conjecture_golf.intake import append_move, prepare_move, validate_move
from conjecture_golf.season_engine import load_compiled_season


def test_intake_validates_and_appends_schema_valid_move(tmp_path):
    transcript = tmp_path / "match.jsonl"
    move = prepare_move({"type": "score"}, player="local-agent")

    _state, verdict = validate_move(transcript, move)
    assert verdict.ok
    assert verdict.kind == "score"

    append_move(transcript, move)
    stored = json.loads(transcript.read_text(encoding="utf-8"))
    assert stored["player"] == "local-agent"


def test_intake_rejects_unknown_counterexample_target(tmp_path):
    transcript = tmp_path / "match.jsonl"
    move = {
        "type": "counterexample",
        "player": "local-agent",
        "against": "missing",
        "before": [".....", ".....", ".....", ".....", "....."],
    }

    _state, verdict = validate_move(transcript, move)

    assert not verdict.ok
    assert verdict.kind == "invalid"


def test_intake_accepts_season_spec(tmp_path):
    transcript = tmp_path / "match.jsonl"
    move = prepare_move({"type": "score"}, player="local-agent")
    season = load_compiled_season("seasons/season_0.json")

    _state, verdict = validate_move(transcript, move, season=season)

    assert verdict.ok
    assert verdict.kind == "score"
