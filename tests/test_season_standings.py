from conjecture_golf.replay import iter_jsonl
from conjecture_golf.season_engine import load_compiled_season
from conjecture_golf.season_standings import build_season_standings, main as standings_main, render_standings_markdown
from conjecture_golf.tournament import run_tournament


def test_season_standings_declares_victory_rule_and_titles():
    result = run_tournament(["rule", "greedy", "counterexample", "characterizer"], rounds=2, seed=0)

    standings = build_season_standings(result.commands, move_cap=16)
    data = standings.to_dict()

    assert data["move_cap"] == 16
    assert data["moves_remaining"] == 8
    assert data["victory_rule"].startswith("Season Champion")
    assert data["leaderboard"][0]["player"]
    assert {race["key"] for race in data["title_races"]} >= {
        "championship",
        "lawwright",
        "refuter",
        "frontier_explorer",
        "characterizer",
        "clean_play",
    }
    assert data["next_objectives"]


def test_season_standings_tracks_secondary_title_metrics():
    result = run_tournament(["rule", "greedy", "counterexample"], rounds=1, seed=0)
    standings = build_season_standings(result.commands, move_cap=12)
    races = {race.key: race for race in standings.title_races}

    assert races["frontier_explorer"].leader == "rule-agent"
    assert races["refuter"].leader == "counterexample-agent"


def test_score_only_observer_is_not_a_title_contender():
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
    contenders = {
        contender["player"]
        for race in standings.title_races
        for contender in race.contenders
    }

    assert "observer" not in contenders
    assert "player" in contenders


def test_season_standings_can_use_explicit_season_spec():
    season = load_compiled_season("seasons/season_0.json")

    standings = build_season_standings(iter_jsonl("examples/transcripts/basic.jsonl"), season=season)

    assert standings.season_id == "season_0"
    assert standings.frontier["total_obligations"] > 0


def test_render_standings_markdown_mentions_title_races():
    standings = build_season_standings(iter_jsonl("examples/transcripts/basic.jsonl"), move_cap=8)

    markdown = render_standings_markdown(standings)

    assert "Season Standings" in markdown
    assert "Title Races" in markdown
    assert "Season Champion" in markdown
    assert "Next Objectives" in markdown


def test_standings_cli_runs_on_basic_transcript(capsys):
    exit_code = standings_main(["examples/transcripts/basic.jsonl", "--move-cap", "8"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Season Standings" in captured.out
    assert "moves remaining" in captured.out
