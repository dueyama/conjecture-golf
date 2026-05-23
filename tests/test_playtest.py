import pytest

from conjecture_golf.playtest import main as playtest_main, render_playtest_markdown, run_playtest


@pytest.fixture(scope="module")
def default_playtest():
    return run_playtest()


def test_playtest_passes_with_default_agent_mix(default_playtest):
    report, commands = default_playtest

    assert report.passed
    assert len(commands) == report.commands
    assert report.criteria["at_least_five_agents"]
    assert report.criteria["has_three_strategic_styles"]
    assert report.criteria["season_not_exhausted"]
    assert report.closed_test_audit["passed"]


def test_playtest_markdown_includes_standings_and_criteria(default_playtest):
    report, _commands = default_playtest

    markdown = render_playtest_markdown(report)

    assert "AI Playtest Report" in markdown
    assert "Season Standings" in markdown
    assert "has_live_title_races" in markdown
    assert "Closed Test Audit" in markdown


def test_playtest_cli_can_write_json(capsys):
    exit_code = playtest_main(["--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"passed": true' in captured.out
    assert '"closed_test_audit"' in captured.out
