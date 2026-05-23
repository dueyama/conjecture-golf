from pathlib import Path

from conjecture_golf import github_issue_handler


def test_issue_handler_excludes_current_comment_by_id_not_body(monkeypatch, tmp_path: Path):
    body = '/cg {"type":"score","player":"repeat"}'
    comments = [
        {
            "id": 1,
            "created_at": "2026-05-14T00:00:00Z",
            "body": body,
            "user": {"login": "same-user"},
        },
        {
            "id": 2,
            "created_at": "2026-05-14T00:30:00Z",
            "body": body,
            "user": {"login": "same-user"},
        },
    ]
    verdict_file = tmp_path / "verdict.md"

    monkeypatch.setattr(github_issue_handler, "fetch_issue_comments", lambda repo, issue_number: comments)
    monkeypatch.setenv("COMMENT_BODY", body)
    monkeypatch.setenv("COMMENT_AUTHOR", "same-user")
    monkeypatch.setenv("COMMENT_CREATED_AT", "2026-05-14T00:30:00Z")
    monkeypatch.setenv("COMMENT_ID", "2")
    monkeypatch.setenv("ISSUE_NUMBER", "7")
    monkeypatch.setenv("GH_REPO", "owner/repo")
    monkeypatch.setenv("CG_MIN_PLAYER_INTERVAL_SECONDS", "3600")
    monkeypatch.setenv("VERDICT_FILE", str(verdict_file))

    assert github_issue_handler.main() == 0
    assert "moved too soon" in verdict_file.read_text(encoding="utf-8")


def test_issue_handler_arena_gate_quarantines_malformed_current_command(monkeypatch, tmp_path: Path):
    verdict_file = tmp_path / "verdict.md"
    canonical_file = tmp_path / "canonical.jsonl"
    quarantine_file = tmp_path / "quarantine.jsonl"
    decision_file = tmp_path / "routing.json"
    branch_store = tmp_path / "branch-store"

    monkeypatch.setattr(github_issue_handler, "fetch_issue_comments", lambda repo, issue_number: [])
    monkeypatch.setenv("COMMENT_BODY", "/cg {not json}")
    monkeypatch.setenv("COMMENT_AUTHOR", "noisy-user")
    monkeypatch.setenv("COMMENT_CREATED_AT", "2026-05-14T00:30:00Z")
    monkeypatch.setenv("COMMENT_ID", "3")
    monkeypatch.setenv("ISSUE_NUMBER", "7")
    monkeypatch.setenv("GH_REPO", "owner/repo")
    monkeypatch.setenv("VERDICT_FILE", str(verdict_file))
    monkeypatch.setenv("CG_CANONICAL_TRANSCRIPT_FILE", str(canonical_file))
    monkeypatch.setenv("CG_QUARANTINE_TRANSCRIPT_FILE", str(quarantine_file))
    monkeypatch.setenv("CG_ARENA_DECISION_FILE", str(decision_file))
    monkeypatch.setenv("CG_BRANCH_STORE_DIR", str(branch_store))

    assert github_issue_handler.main() == 0

    verdict = verdict_file.read_text(encoding="utf-8")
    assert "Routed to quarantine branch" in verdict
    assert "AI Arena Packet" in verdict
    assert "conjecture_golf.github_arena_turn.v1" in verdict
    assert '"audience": "github_ai_agent"' in verdict
    assert "quarantine/season-0" in verdict
    assert canonical_file.read_text(encoding="utf-8") == ""
    assert '"type":"quarantine"' in quarantine_file.read_text(encoding="utf-8")
    assert '"quarantine_records": 1' in decision_file.read_text(encoding="utf-8")
    assert (branch_store / "arena" / "season-0" / "transcript.jsonl").read_text(encoding="utf-8") == ""
    assert '"noisy-user"' in (
        branch_store / "quarantine" / "season-0" / "quarantine.jsonl"
    ).read_text(encoding="utf-8")
    assert (branch_store / "branch-store-manifest.json").exists()
