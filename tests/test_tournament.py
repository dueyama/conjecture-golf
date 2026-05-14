from pathlib import Path

from conjecture_golf.replay import replay_file
from conjecture_golf.score import leaderboard_rows
from conjecture_golf.tournament import run_tournament, write_jsonl


def test_local_tournament_generates_replayable_transcript(tmp_path: Path):
    result = run_tournament(["rule", "greedy", "counterexample"], rounds=2, seed=0)
    transcript = tmp_path / "match.jsonl"
    write_jsonl(result.commands, transcript)

    replayed = replay_file(transcript, season_scoring=True)
    assert [v.to_dict() for v in replayed.verdicts] == [v.to_dict() for v in result.state.verdicts]


def test_counterexample_agent_refutes_greedy_agent():
    result = run_tournament(["greedy", "counterexample"], rounds=1, seed=0)
    rows = leaderboard_rows(result.state.scores)

    assert rows[0]["player"] == "counterexample-agent"
    assert rows[0]["valid_counterexamples"] == 1


def test_rule_agent_baselines_are_valid_for_their_first_cycle():
    result = run_tournament(["rule"], rounds=4, seed=0)
    rows = leaderboard_rows(result.state.scores)

    assert rows[0]["player"] == "rule-agent"
    assert rows[0]["total"] > 0
    assert rows[0]["valid_conjectures"] == 4
    assert rows[0]["valid_counterexamples"] == 0
    assert rows[0]["invalid_moves"] == 0


def test_copycat_agent_cannot_profit_from_repeating_existing_law():
    result = run_tournament(["rule", "copycat"], rounds=1, seed=0)
    rows = {row["player"]: row for row in leaderboard_rows(result.state.scores)}

    assert rows["copycat-agent"]["total"] <= 0
    assert rows["copycat-agent"]["invalid_moves"] == 1


def test_narrow_spam_agent_gets_no_points_for_stale_specialization():
    result = run_tournament(["rule", "narrow_spam"], rounds=1, seed=0)
    rows = {row["player"]: row for row in leaderboard_rows(result.state.scores)}

    assert rows["narrow_spam-agent"]["total"] == 0
    assert rows["narrow_spam-agent"]["valid_conjectures"] == 1
