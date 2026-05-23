from pathlib import Path

from conjecture_golf.replay import replay_file
from conjecture_golf.score import leaderboard_rows
from conjecture_golf.local_agents import available_agents
from conjecture_golf.tournament import run_tournament, write_jsonl


def test_builtin_agents_include_distinct_strategy_roles():
    agents = set(available_agents())

    assert {"rule", "frontier", "characterizer", "greedy", "counterexample", "original_refuter", "minimalist"} <= agents


def test_local_tournament_generates_replayable_transcript(tmp_path: Path):
    result = run_tournament(["rule", "greedy", "counterexample"], rounds=2, seed=0)
    transcript = tmp_path / "match.jsonl"
    write_jsonl(result.commands, transcript)

    replayed = replay_file(transcript, season_scoring=True)
    assert [v.to_dict() for v in replayed.verdicts] == [v.to_dict() for v in result.state.verdicts]


def test_tournament_writer_creates_parent_directories(tmp_path: Path):
    result = run_tournament(["rule"], rounds=1, seed=0)
    transcript = tmp_path / "nested" / "match.jsonl"

    write_jsonl(result.commands, transcript)

    assert transcript.exists()


def test_counterexample_agent_refutes_greedy_agent():
    result = run_tournament(["greedy", "counterexample"], rounds=1, seed=0)
    rows = leaderboard_rows(result.state.scores)

    assert rows[0]["player"] == "counterexample-agent"
    assert rows[0]["valid_counterexamples"] == 1


def test_original_refuter_avoids_verifier_revealed_witness():
    result = run_tournament(["greedy", "original_refuter"], rounds=1, seed=0)
    counter = result.commands[-1]
    verdict = result.state.verdicts[-1]

    assert counter["type"] == "counterexample"
    assert verdict.details["season_score_basis"] == "novel_first_counterexample"


def test_rule_agent_baselines_are_valid_for_their_first_cycle():
    result = run_tournament(["rule"], rounds=4, seed=0)
    rows = leaderboard_rows(result.state.scores)

    assert rows[0]["player"] == "rule-agent"
    assert rows[0]["total"] > 0
    assert rows[0]["valid_conjectures"] == 4
    assert rows[0]["valid_counterexamples"] == 0
    assert rows[0]["invalid_moves"] == 0


def test_frontier_agent_opens_distinct_valid_territory():
    result = run_tournament(["rule", "frontier"], rounds=2, seed=0)
    rows = {row["player"]: row for row in leaderboard_rows(result.state.scores)}

    assert rows["frontier-agent"]["total"] > 0
    assert rows["frontier-agent"]["valid_conjectures"] == 2
    assert rows["frontier-agent"]["invalid_moves"] == 0


def test_minimalist_agent_prefers_sharpest_available_counterexample():
    result = run_tournament(["greedy", "random", "minimalist"], rounds=1, seed=0)
    counter = result.commands[-1]
    rows = {row["player"]: row for row in leaderboard_rows(result.state.scores)}

    assert counter["type"] == "counterexample"
    assert counter["against"].startswith("random_0_")
    assert rows["minimalist-agent"]["valid_counterexamples"] == 1


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
