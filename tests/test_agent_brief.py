from conjecture_golf.agent_brief import build_agent_brief, main as brief_main, render_agent_brief_markdown
from conjecture_golf.replay import replay_records
from conjecture_golf.season_standings import build_season_standings
from conjecture_golf.tournament import run_tournament, write_jsonl


def test_agent_brief_summarizes_next_move_pressure():
    result = run_tournament(["rule", "frontier", "characterizer", "minimalist"], rounds=1, seed=0)
    standings = build_season_standings(result.commands, move_cap=12)
    state = replay_records(result.commands, season_scoring=True)

    brief = build_agent_brief(standings, player="minimalist-agent", recent_verdicts=state.verdicts)

    assert brief["player"] == "minimalist-agent"
    assert brief["leader"]
    assert brief["top_open_frontier"]
    assert brief["recommendations"]
    assert "title_opportunities" in brief
    assert brief["recent_feedback"]
    assert any(item.startswith("Output exactly one JSON object") for item in brief["submission_contract"])

    leader_brief = build_agent_brief(standings, player=brief["leader"]["player"], recent_verdicts=state.verdicts)
    assert leader_brief["title_opportunities"]


def test_agent_brief_flags_unqualified_player():
    standings = build_season_standings(
        [
            {"type": "score", "player": "observer"},
            {
                "type": "conjecture",
                "player": "player",
                "name": "stone_stays_stone",
                "if": [{"target_is": "S"}],
                "then": {"target_becomes": "S"},
            },
        ]
    )

    brief = build_agent_brief(standings, player="observer")
    markdown = render_agent_brief_markdown(brief)

    assert "Qualify for title races" in brief["recommendations"][0]
    assert "not qualified" in markdown
    assert "Your Title Opportunities" in markdown


def test_agent_brief_cli_can_render_json(tmp_path, capsys):
    result = run_tournament(["rule", "greedy", "minimalist"], rounds=1, seed=0)
    transcript = tmp_path / "match.jsonl"
    write_jsonl(result.commands, transcript)

    exit_code = brief_main([str(transcript), "--player", "minimalist-agent", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"player": "minimalist-agent"' in captured.out
    assert '"submission_contract"' in captured.out
