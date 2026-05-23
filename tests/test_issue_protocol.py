import pytest

from conjecture_golf.issue_protocol import commands_from_issue_comments, parse_issue_comment, render_verdict_markdown
from conjecture_golf.replay import ReplayState
from conjecture_golf.verify import Verdict
from conjecture_golf.world import ValidationError


def test_parse_valid_issue_command():
    text = '/cg {"type":"score","player":"observer"}'
    result = parse_issue_comment(text)
    assert result.accepted
    assert result.parsed.command["type"] == "score"


def test_parse_valid_hello_issue_command():
    text = (
        '/cg {"type":"hello","player":"codex-local",'
        '"agent_profile":{"kind":"llm_agent","autonomy":"human_approved"}}'
    )
    result = parse_issue_comment(text)
    assert result.accepted
    assert result.parsed.command["type"] == "hello"


def test_ignore_non_command():
    result = parse_issue_comment("hello")
    assert not result.accepted


def test_reject_malformed_json():
    with pytest.raises(ValidationError):
        parse_issue_comment("/cg {not json}")


def test_reject_user_supplied_transcript_metadata():
    with pytest.raises(ValidationError):
        parse_issue_comment('/cg {"type":"score","player":"p","_meta":{"created_at":"2026-05-14T00:00:00Z"}}')


def test_reject_unknown_score_command_field():
    with pytest.raises(ValidationError):
        parse_issue_comment('/cg {"type":"score","player":"p","bonus":999}')


def test_reject_ambiguous_counterexample_board_sources():
    text = (
        '/cg {"type":"counterexample","player":"p","against":"c",'
        '"before":[".....",".....",".....",".....","....."],'
        '"board":[".....",".....",".....",".....","....."]}'
    )
    with pytest.raises(ValidationError):
        parse_issue_comment(text)


def test_reject_bot_comment():
    result = parse_issue_comment('/cg {"type":"score"}', author_login="github-actions[bot]")
    assert not result.accepted


def test_render_verdict_markdown_contains_score():
    verdict = Verdict(ok=True, kind="score", message="ok", player="p", score_delta=3, details={"x": 1})
    md = render_verdict_markdown(verdict)
    assert "Score delta" in md
    assert "```json" in md


def test_render_verdict_markdown_can_redact_counterexample():
    verdict = Verdict(
        ok=False,
        kind="conjecture",
        message="false",
        player="p",
        score_delta=-5,
        details={
            "counterexample": {
                "board": [".....", ".....", ".....", ".SFW.", "....."],
                "expected": "F",
                "actual": ".",
            }
        },
    )

    md = render_verdict_markdown(verdict, reveal_policy="redacted")

    assert ".SFW." not in md
    assert "counterexample_digest" in md
    assert "counterexample_redacted" in md


def test_commands_from_issue_comments_attach_public_metadata():
    comments = [
        {
            "id": 123,
            "created_at": "2026-05-14T00:00:00Z",
            "body": '/cg {"type":"score","player":"observer"}',
            "user": {"login": "human"},
        }
    ]

    commands = commands_from_issue_comments(comments)

    assert commands[0]["_meta"]["source"] == "github_issue"
    assert commands[0]["_meta"]["created_at"] == "2026-05-14T00:00:00Z"
    assert commands[0]["_meta"]["comment_id"] == 123
    assert commands[0]["_meta"]["author_login"] == "human"


def test_malformed_issue_command_becomes_invalid_transcript_record():
    comments = [
        {
            "id": 124,
            "created_at": "2026-05-14T00:00:00Z",
            "body": "/cg {not json}",
            "user": {"login": "human"},
        }
    ]

    commands = commands_from_issue_comments(comments)

    assert commands[0]["type"] == "invalid"
    assert commands[0]["player"] == "human"
    assert commands[0]["reason"] == "malformed_issue_comment"


def test_schema_invalid_issue_command_becomes_invalid_transcript_record():
    comments = [
        {
            "id": 125,
            "created_at": "2026-05-14T00:00:00Z",
            "body": '/cg {"type":"score","player":"human","bonus":999}',
            "user": {"login": "human"},
        }
    ]

    commands = commands_from_issue_comments(comments)

    assert commands[0]["type"] == "invalid"
    assert commands[0]["player"] == "human"
    assert "unknown score command fields" in commands[0]["message"]
