"""Deterministic local playtest for AI-agent game quality."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .closed_test_audit import audit_state
from .season_eval import evaluate_state
from .season_standings import build_season_standings_from_state
from .tournament import run_tournament, write_jsonl

DEFAULT_PLAYTEST_AGENTS = [
    "rule",
    "frontier",
    "characterizer",
    "greedy",
    "original_refuter",
    "minimalist",
    "random",
]


@dataclass(frozen=True)
class PlaytestReport:
    agents: list[str]
    rounds: int
    seed: int
    move_cap: int
    commands: int
    passed: bool
    criteria: dict[str, bool]
    standings: dict[str, Any]
    evaluation: dict[str, Any]
    closed_test_audit: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "agents": self.agents,
            "rounds": self.rounds,
            "seed": self.seed,
            "move_cap": self.move_cap,
            "commands": self.commands,
            "passed": self.passed,
            "criteria": self.criteria,
            "standings": self.standings,
            "evaluation": self.evaluation,
            "closed_test_audit": self.closed_test_audit,
        }


def run_playtest(
    *,
    agents: list[str] | None = None,
    rounds: int = 2,
    seed: int = 0,
    move_cap: int = 24,
) -> tuple[PlaytestReport, list[dict[str, Any]]]:
    agent_names = agents or list(DEFAULT_PLAYTEST_AGENTS)
    result = run_tournament(agent_names, rounds=rounds, seed=seed, season_scoring=True)
    standings = build_season_standings_from_state(result.state, move_cap=move_cap)
    evaluation = evaluate_state(result.state)
    closed_test_audit = audit_state(result.state, standings=standings, move_cap=move_cap)
    standings_data = standings.to_dict()
    evaluation_data = evaluation.to_dict()
    led_title_races = sum(1 for race in standings_data["title_races"] if race["leader"])
    distinct_title_leaders = {
        race["leader"]
        for race in standings_data["title_races"]
        if race["leader"] is not None
    }
    criteria = {
        "at_least_five_agents": len(agent_names) >= 5,
        "has_valid_conjecture": evaluation_data["valid_conjectures"] > 0,
        "has_valid_counterexample": evaluation_data["valid_counterexamples"] > 0,
        "has_risky_or_invalid_pressure": evaluation_data["invalid_moves"] > 0,
        "has_three_strategic_styles": len(evaluation_data["strategic_styles"]) >= 3,
        "has_live_title_races": led_title_races >= 4 and len(distinct_title_leaders) >= 3,
        "has_next_objectives": bool(standings_data["next_objectives"]),
        "season_not_exhausted": (
            standings_data["moves_remaining"] > 0
            and standings_data["frontier"]["coverage_ratio"] < standings_data["coverage_target_ratio"]
        ),
    }
    report = PlaytestReport(
        agents=agent_names,
        rounds=rounds,
        seed=seed,
        move_cap=move_cap,
        commands=len(result.commands),
        passed=all(criteria.values()),
        criteria=criteria,
        standings=standings_data,
        evaluation=evaluation_data,
        closed_test_audit=closed_test_audit.to_dict(),
    )
    return report, result.commands


def render_playtest_markdown(report: PlaytestReport) -> str:
    data = report.to_dict()
    standings = data["standings"]
    lines = [
        "# AI Playtest Report",
        "",
        f"Agents: `{', '.join(data['agents'])}`",
        f"Rounds: `{data['rounds']}`",
        f"Commands: `{data['commands']}`",
        f"Passed: `{str(data['passed']).lower()}`",
        "",
        "## Criteria",
        "",
        "| criterion | passed |",
        "| --- | ---: |",
    ]
    for key, passed in data["criteria"].items():
        lines.append(f"| {key} | {str(passed).lower()} |")
    lines.extend(
        [
            "",
            "## Styles",
            "",
        ]
    )
    styles = data["evaluation"]["strategic_styles"]
    if styles:
        lines.extend(f"- `{style}`" for style in styles)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Season Standings",
            "",
            f"Phase: `{standings['phase']}`",
            f"Moves remaining: `{standings['moves_remaining']}`",
            f"Coverage ratio: `{standings['frontier']['coverage_ratio']:.6f}`",
            "",
            "| title | leader | value |",
            "| --- | --- | ---: |",
        ]
    )
    for race in standings["title_races"]:
        leader = race["leader"] or "-"
        value = race["value"] if race["value"] is not None else "-"
        lines.append(f"| {race['title']} | `{leader}` | {value} |")
    lines.extend(["", "## Next Objectives", ""])
    for objective in standings["next_objectives"]:
        lines.append(f"- {objective}")
    audit = data["closed_test_audit"]
    lines.extend(["", "## Closed Test Audit", ""])
    lines.append(f"Passed: `{str(audit['passed']).lower()}`")
    for check in audit["checks"]:
        lines.append(f"- `{check['key']}`: `{str(check['passed']).lower()}`")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a deterministic local AI playtest.")
    parser.add_argument("--agent", action="append", dest="agents", help="Agent to include. May be repeated.")
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--move-cap", type=int, default=24)
    parser.add_argument("--out-transcript", help="Optional JSONL transcript output path.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    args = parser.parse_args(argv)

    report, commands = run_playtest(
        agents=args.agents,
        rounds=args.rounds,
        seed=args.seed,
        move_cap=args.move_cap,
    )
    if args.out_transcript:
        write_jsonl(commands, Path(args.out_transcript))
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_playtest_markdown(report))
    return 0 if report.passed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
