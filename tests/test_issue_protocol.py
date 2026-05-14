import pytest

from conjecture_golf.issue_protocol import parse_issue_comment, render_verdict_markdown
from conjecture_golf.replay import ReplayState
from conjecture_golf.verify import Verdict
from conjecture_golf.world import ValidationError


def test_parse_valid_issue_command():
    text = '/cg {"type":"score","player":"observer"}'
    result = parse_issue_comment(text)
    assert result.accepted
    assert result.parsed.command["type"] == "score"


def test_ignore_non_command():
    result = parse_issue_comment("hello")
    assert not result.accepted


def test_reject_malformed_json():
    with pytest.raises(ValidationError):
        parse_issue_comment("/cg {not json}")


def test_reject_bot_comment():
    result = parse_issue_comment('/cg {"type":"score"}', author_login="github-actions[bot]")
    assert not result.accepted


def test_render_verdict_markdown_contains_score():
    verdict = Verdict(ok=True, kind="score", message="ok", player="p", score_delta=3, details={"x": 1})
    md = render_verdict_markdown(verdict)
    assert "Score delta" in md
    assert "```json" in md
