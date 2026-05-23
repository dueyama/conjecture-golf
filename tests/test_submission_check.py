import json

from conjecture_golf.submission_check import check_submission, main as submission_check_main, render_submission_report


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


def _quarantine(player: str) -> dict:
    return {
        "type": "quarantine",
        "player": player,
        "reason": "invalid_move",
        "verdict": {
            "ok": False,
            "kind": "invalid",
            "player": player,
            "message": "bad command",
            "score_delta": 0,
            "details": {},
        },
        "command": {"type": "invalid", "player": player},
    }


def test_submission_check_accepts_valid_move_for_expected_player(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("", encoding="utf-8")

    report = check_submission(transcript, TRUE_FLOWER, expected_player="blue")

    assert report["accepted"] is True
    assert report["player"] == "blue"
    assert report["player_matches_expected"] is True
    assert report["verdict"]["kind"] == "conjecture"
    assert "Accepted: `true`" in render_submission_report(report)


def test_submission_check_rejects_player_mismatch(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("", encoding="utf-8")

    report = check_submission(transcript, TRUE_FLOWER, expected_player="red")

    assert report["accepted"] is False
    assert report["status"] == "player_mismatch"
    assert report["player_matches_expected"] is False
    assert any("player mismatch" in warning for warning in report["warnings"])


def test_submission_check_applies_quarantine_gate(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("", encoding="utf-8")
    report = check_submission(
        transcript,
        {"type": "score", "player": "noise"},
        quarantine_records=[_quarantine("noise"), _quarantine("noise"), _quarantine("noise")],
    )

    assert report["accepted"] is False
    assert report["status"] == "quarantined"
    assert report["route"]["reason"] == "player_disqualified"


def test_submission_check_cli_reports_invalid_json(tmp_path, capsys):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("", encoding="utf-8")
    move = tmp_path / "move.md"
    move.write_text("```json\n{}\n```", encoding="utf-8")

    exit_code = submission_check_main([str(transcript), str(move), "--expected-player", "blue", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert '"status": "invalid_json"' in captured.out


def test_submission_check_cli_accepts_json(tmp_path, capsys):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("", encoding="utf-8")
    move = tmp_path / "move.json"
    move.write_text(json.dumps(TRUE_FLOWER), encoding="utf-8")

    exit_code = submission_check_main([str(transcript), str(move), "--expected-player", "blue", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"accepted": true' in captured.out
