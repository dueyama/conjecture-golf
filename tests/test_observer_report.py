from conjecture_golf.observer_report import render_html_report, render_report
from conjecture_golf.season_engine import load_compiled_season

HELLO_CODEX = {
    "type": "hello",
    "player": "codex-local",
    "agent_profile": {
        "kind": "llm_agent",
        "model_family": "gpt",
        "model_name": "GPT-5.5",
        "interface": "Codex desktop",
        "autonomy": "human_approved",
        "can_read_repo": True,
        "can_run_tests": True,
        "can_post_to_github": True,
    },
}


def test_observer_report_mentions_arc_and_leaderboard():
    records = [
        {
            "type": "conjecture",
            "player": "red",
            "name": "too_broad",
            "if": [
                {"target_is": "."},
                {"exists": {"symbol": "W", "relation": "diagonal"}},
                {"exists": {"symbol": "F", "relation": "orthogonal"}},
            ],
            "then": {"target_becomes": "F"},
        },
        {
            "type": "counterexample",
            "player": "green",
            "against": "too_broad",
            "before": [".W...", ".....", ".SF..", ".....", "....."],
        },
    ]

    report = render_report(records)

    assert "Observer Report" in report
    assert "Move 1" in report
    assert "green" in report
    assert "conjecture-counterexample arc" in report
    assert "| rank | player | total |" in report


def test_observer_report_renders_agent_profiles():
    report = render_report([HELLO_CODEX])

    assert "Registered Agents" in report
    assert "codex-local" in report
    assert "GPT-5.5" in report
    assert "self-reported" in report


def test_observer_report_accepts_season_spec():
    season = load_compiled_season("seasons/season_0.json")
    report = render_report(
        [
            {
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
        ],
        season_scoring=True,
        season=season,
    )

    assert "Season: `season_0`" in report
    assert "Season novelty" in report


def test_observer_report_can_redact_false_conjecture_witnesses():
    records = [
        {
            "type": "conjecture",
            "player": "red",
            "name": "too_broad",
            "if": [
                {"target_is": "."},
                {"exists": {"symbol": "W", "relation": "diagonal"}},
                {"exists": {"symbol": "F", "relation": "orthogonal"}},
            ],
            "then": {"target_becomes": "F"},
        }
    ]

    report = render_report(records, reveal_policy="redacted")

    assert "A witness exists but is redacted" in report
    assert ".SFW." not in report


def test_html_observer_report_renders_counterexample_boards():
    records = [
        {
            "type": "conjecture",
            "player": "red",
            "name": "too_broad",
            "if": [
                {"target_is": "."},
                {"exists": {"symbol": "W", "relation": "diagonal"}},
                {"exists": {"symbol": "F", "relation": "orthogonal"}},
            ],
            "then": {"target_becomes": "F"},
        },
        {
            "type": "counterexample",
            "player": "green",
            "against": "too_broad",
            "before": [".W...", ".....", ".SF..", ".....", "....."],
        },
    ]

    html = render_html_report(records)

    assert "<!doctype html>" in html
    assert 'class="board"' in html
    assert "symbol-F" in html
    assert "Leaderboard" in html
