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


def test_issue_handler_closed_season_does_not_fetch_or_write_streams(monkeypatch, tmp_path: Path):
    verdict_file = tmp_path / "verdict.md"

    def fail_fetch(repo, issue_number):  # pragma: no cover - called only on regression
        raise AssertionError("closed seasons must not fetch issue comments")

    monkeypatch.setattr(github_issue_handler, "fetch_issue_comments", fail_fetch)
    monkeypatch.setenv("COMMENT_BODY", '/cg {"type":"score","player":"late"}')
    monkeypatch.setenv("COMMENT_AUTHOR", "late-user")
    monkeypatch.setenv("COMMENT_CREATED_AT", "2026-06-19T00:30:00Z")
    monkeypatch.setenv("COMMENT_ID", "30")
    monkeypatch.setenv("ISSUE_NUMBER", "1")
    monkeypatch.setenv("GH_REPO", "owner/repo")
    monkeypatch.setenv("CG_ARENA_STATUS", "closed")
    monkeypatch.setenv("CG_ACTIVE_ARENA_URL", "https://github.com/dueyama/conjecture-golf/issues/2")
    monkeypatch.setenv("VERDICT_FILE", str(verdict_file))
    monkeypatch.setenv("CG_CANONICAL_TRANSCRIPT_FILE", str(tmp_path / "canonical.jsonl"))
    monkeypatch.setenv("CG_QUARANTINE_TRANSCRIPT_FILE", str(tmp_path / "quarantine.jsonl"))

    assert github_issue_handler.main() == 0

    verdict = verdict_file.read_text(encoding="utf-8")
    assert "season closed" in verdict
    assert "Current arena information" in verdict
    assert "issues/2" in verdict
    assert not (tmp_path / "canonical.jsonl").exists()
    assert not (tmp_path / "quarantine.jsonl").exists()


def test_issue_handler_closed_season_1_archive_does_not_fetch_or_write_streams(
    monkeypatch, tmp_path: Path
):
    verdict_file = tmp_path / "verdict.md"

    def fail_fetch(repo, issue_number):  # pragma: no cover - called only on regression
        raise AssertionError("closed seasons must not fetch issue comments")

    monkeypatch.setattr(github_issue_handler, "fetch_issue_comments", fail_fetch)
    monkeypatch.setenv("COMMENT_BODY", '/cg {"type":"score","player":"late-season-1"}')
    monkeypatch.setenv("COMMENT_AUTHOR", "late-user")
    monkeypatch.setenv("COMMENT_CREATED_AT", "2026-07-02T10:00:00Z")
    monkeypatch.setenv("COMMENT_ID", "90")
    monkeypatch.setenv("ISSUE_NUMBER", "2")
    monkeypatch.setenv("GH_REPO", "owner/repo")
    monkeypatch.setenv("CG_ARENA_STATUS", "closed")
    monkeypatch.setenv("CG_ARENA_STATUS_MESSAGE", "Season 1 is closed.")
    monkeypatch.setenv("CG_ACTIVE_ARENA_URL", "https://github.com/dueyama/conjecture-golf")
    monkeypatch.setenv("VERDICT_FILE", str(verdict_file))
    monkeypatch.setenv("CG_CANONICAL_TRANSCRIPT_FILE", str(tmp_path / "canonical.jsonl"))
    monkeypatch.setenv("CG_QUARANTINE_TRANSCRIPT_FILE", str(tmp_path / "quarantine.jsonl"))

    assert github_issue_handler.main() == 0

    verdict = verdict_file.read_text(encoding="utf-8")
    assert "season closed" in verdict
    assert "Season 1 is closed." in verdict
    assert "Current arena information" in verdict
    assert not (tmp_path / "canonical.jsonl").exists()
    assert not (tmp_path / "quarantine.jsonl").exists()


def test_issue_workflow_routes_season_1_issue_as_closed_archive():
    workflow = Path(".github/workflows/issue-comment.yml").read_text(encoding="utf-8")
    season_1_block = workflow.split('elif issue_number == "2"')[1].split('elif issue_number == "3"')[0]

    assert 'status="closed"' in season_1_block
    assert 'rules_ref="main"' in season_1_block
    assert 'message="Season 1 is closed.' in season_1_block
    assert 'status="active"' not in season_1_block


def test_issue_workflow_routes_season_2_issue_as_active_arena():
    workflow = Path(".github/workflows/issue-comment.yml").read_text(encoding="utf-8")
    season_2_block = workflow.split('elif issue_number == "3"')[1].split("with open")[0]

    assert 'status="active"' in season_2_block
    assert 'rules_ref="season-2-rules"' in season_2_block
    assert 'season_spec="seasons/season_2.json"' in season_2_block
    assert 'canonical_branch="arena/season-2"' in season_2_block
    assert 'quarantine_branch="quarantine/season-2"' in season_2_block


def test_issue_handler_active_season_1_packet_uses_season_spec(monkeypatch, tmp_path: Path):
    verdict_file = tmp_path / "verdict.md"
    canonical_file = tmp_path / "canonical.jsonl"
    quarantine_file = tmp_path / "quarantine.jsonl"
    decision_file = tmp_path / "routing.json"
    branch_store = tmp_path / "branch-store"

    monkeypatch.setattr(github_issue_handler, "fetch_issue_comments", lambda repo, issue_number: [])
    monkeypatch.setenv("COMMENT_BODY", '/cg {"type":"score","player":"observer"}')
    monkeypatch.setenv("COMMENT_AUTHOR", "observer")
    monkeypatch.setenv("COMMENT_CREATED_AT", "2026-06-19T00:30:00Z")
    monkeypatch.setenv("COMMENT_ID", "31")
    monkeypatch.setenv("ISSUE_NUMBER", "2")
    monkeypatch.setenv("GH_REPO", "owner/repo")
    monkeypatch.setenv("CG_SEASON_SPEC", "seasons/season_1.json")
    monkeypatch.setenv("CG_CANONICAL_BRANCH", "arena/season-1")
    monkeypatch.setenv("CG_QUARANTINE_BRANCH", "quarantine/season-1")
    monkeypatch.setenv("VERDICT_FILE", str(verdict_file))
    monkeypatch.setenv("CG_CANONICAL_TRANSCRIPT_FILE", str(canonical_file))
    monkeypatch.setenv("CG_QUARANTINE_TRANSCRIPT_FILE", str(quarantine_file))
    monkeypatch.setenv("CG_ARENA_DECISION_FILE", str(decision_file))
    monkeypatch.setenv("CG_BRANCH_STORE_DIR", str(branch_store))

    assert github_issue_handler.main() == 0

    verdict = verdict_file.read_text(encoding="utf-8")
    assert "arena/season-1" in verdict
    assert '"season_id": "season_1"' in verdict
    assert '"symbols": [' in verdict
    assert '"M"' in verdict
    assert canonical_file.read_text(encoding="utf-8").count("\n") == 1
    assert (branch_store / "arena" / "season-1" / "transcript.jsonl").exists()
