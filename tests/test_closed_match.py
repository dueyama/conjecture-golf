import json

from conjecture_golf.closed_match import main as closed_match_main, run_closed_match


TRUE_FLOWER = {
    "type": "conjecture",
    "player": "careful",
    "name": "flower_growth",
    "if": [
        {"target_is": "."},
        {"exists": {"symbol": "W", "relation": "diagonal"}},
        {"exists": {"symbol": "F", "relation": "orthogonal"}},
        {"not_exists": {"symbol": "S", "relation": "king"}},
    ],
    "then": {"target_becomes": "F"},
}


def test_closed_match_routes_directory_moves(tmp_path):
    transcript = tmp_path / "start.jsonl"
    transcript.write_text("", encoding="utf-8")
    moves = tmp_path / "moves"
    moves.mkdir()
    (moves / "01-careful.json").write_text(json.dumps(TRUE_FLOWER), encoding="utf-8")
    (moves / "02-noise.json").write_text("{not json}", encoding="utf-8")

    result = run_closed_match(transcript, moves)

    assert result.accepted_count == 1
    assert result.rejected_count == 1
    assert len(result.canonical_records) == 1
    assert len(result.quarantine_records) == 1
    assert result.decisions[0].branch == "arena/season-0"
    assert result.decisions[1].branch == "quarantine/season-0"


def test_closed_match_carries_prior_quarantine_strikes(tmp_path):
    transcript = tmp_path / "start.jsonl"
    transcript.write_text("", encoding="utf-8")
    moves = tmp_path / "moves"
    moves.mkdir()
    (moves / "noise.json").write_text(json.dumps({**TRUE_FLOWER, "player": "noise"}), encoding="utf-8")
    prior_quarantine = [
        {
            "type": "quarantine",
            "player": "noise",
            "reason": "invalid_move",
            "strikes_after": strike,
            "verdict": {"kind": "invalid", "player": "noise"},
            "command": {"type": "score", "player": "noise", "bonus": 999},
        }
        for strike in (1, 2, 3)
    ]

    result = run_closed_match(transcript, moves, prior_quarantine_records=prior_quarantine)

    assert result.accepted_count == 0
    assert result.rejected_count == 1
    assert result.decisions[0].reason == "player_disqualified"
    assert len(result.canonical_records) == 0
    assert len(result.quarantine_records) == 4


def test_closed_match_cli_writes_round_outputs(tmp_path, capsys):
    transcript = tmp_path / "start.jsonl"
    transcript.write_text("", encoding="utf-8")
    moves = tmp_path / "moves"
    out = tmp_path / "out"
    moves.mkdir()
    (moves / "01-careful.json").write_text(json.dumps(TRUE_FLOWER), encoding="utf-8")

    exit_code = closed_match_main([str(transcript), str(moves), "--out", str(out)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"accepted_count": 1' in captured.out
    assert (out / "canonical.jsonl").exists()
    assert (out / "quarantine.jsonl").exists()
    assert (out / "round_report.md").exists()
    assert "Closed Match Round Report" in (out / "round_report.md").read_text(encoding="utf-8")
    assert (out / "agent_brief.md").exists()
    assert (out / "frontier.md").exists()
    assert (out / "observer_report.md").exists()
    assert "Match story" in (out / "observer_report.md").read_text(encoding="utf-8")
    assert (out / "season_eval.json").exists()
    evaluation = json.loads((out / "season_eval.json").read_text(encoding="utf-8"))
    assert "style_notes_by_player" in evaluation
    assert (out / "player_briefs" / "index.json").exists()
    assert "Recent Feedback" in (out / "player_briefs" / "careful.md").read_text(encoding="utf-8")
