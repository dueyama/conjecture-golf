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
