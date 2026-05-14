"""Generate deterministic local Conjecture Golf transcripts."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .local_agents import available_agents, next_agent_command
from .replay import ReplayState, apply_command
from .score import leaderboard_rows, render_markdown


@dataclass(frozen=True)
class TournamentResult:
    commands: list[dict[str, Any]]
    state: ReplayState


def run_tournament(
    agent_names: list[str],
    *,
    rounds: int = 3,
    seed: int = 0,
    season_scoring: bool = True,
) -> TournamentResult:
    if rounds < 1:
        raise ValueError("rounds must be at least 1")
    known_agents = set(available_agents())
    unknown = sorted(set(agent_names) - known_agents)
    if unknown:
        raise ValueError(f"unknown agents: {unknown}; choose from {sorted(known_agents)}")

    state = ReplayState()
    commands: list[dict[str, Any]] = []
    for turn_index in range(rounds):
        for agent_name in agent_names:
            player = f"{agent_name}-agent"
            command = next_agent_command(
                agent_name,
                player=player,
                state=state,
                prior_commands=commands,
                turn_index=turn_index,
                seed=seed,
            )
            commands.append(command)
            apply_command(state, command, season_scoring=season_scoring)
    return TournamentResult(commands=commands, state=state)


def write_jsonl(commands: list[dict[str, Any]], path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8") as f:
        for command in commands:
            f.write(json.dumps(command, ensure_ascii=False, separators=(",", ":")))
            f.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a deterministic local Conjecture Golf tournament.")
    parser.add_argument(
        "--agent",
        action="append",
        dest="agents",
        choices=available_agents(),
        help="Built-in local agent to include. May be passed multiple times.",
    )
    parser.add_argument("--rounds", type=int, default=3, help="Number of turns per agent.")
    parser.add_argument("--seed", type=int, default=0, help="Deterministic seed for random agents.")
    parser.add_argument("--out", help="Optional transcript JSONL output path.")
    parser.add_argument("--json", action="store_true", help="Print commands and verdicts as JSON.")
    parser.add_argument("--raw-scoring", action="store_true", help="Disable season novelty scoring.")
    args = parser.parse_args(argv)

    agent_names = args.agents or ["rule", "characterizer", "greedy", "counterexample", "random"]
    result = run_tournament(agent_names, rounds=args.rounds, seed=args.seed, season_scoring=not args.raw_scoring)

    if args.out:
        write_jsonl(result.commands, args.out)

    if args.json:
        print(
            json.dumps(
                {
                    "commands": result.commands,
                    "leaderboard": leaderboard_rows(result.state.scores),
                    "verdicts": [verdict.to_dict() for verdict in result.state.verdicts],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        if args.out:
            print(f"Wrote transcript: {args.out}")
        print(render_markdown(leaderboard_rows(result.state.scores)))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
