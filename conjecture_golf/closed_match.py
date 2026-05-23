"""Batch-run a closed Conjecture Golf round from submitted JSON moves."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .agent_brief import build_agent_brief, render_agent_brief_markdown
from .arena_gate import GateDecision, gate_move, iter_quarantine_jsonl
from .frontier import build_frontier_report_from_records, render_frontier_markdown
from .intake import load_move
from .observer_report import render_html_report, render_report
from .replay import iter_jsonl, replay_records
from .season_catalog import load_optional_compiled_season
from .season_engine import CompiledSeason
from .season_eval import evaluate_records, render_evaluation_markdown
from .season_standings import build_season_standings, render_standings_markdown
from .world import ValidationError


@dataclass(frozen=True)
class ClosedMatchResult:
    canonical_records: list[dict[str, Any]]
    quarantine_records: list[dict[str, Any]]
    decisions: list[GateDecision]

    @property
    def accepted_count(self) -> int:
        return sum(1 for decision in self.decisions if decision.accepted)

    @property
    def rejected_count(self) -> int:
        return sum(1 for decision in self.decisions if not decision.accepted)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "canonical_records": len(self.canonical_records),
            "quarantine_records": len(self.quarantine_records),
            "decisions": [decision.to_dict() for decision in self.decisions],
        }


def _write_json(path: str | Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: str | Path, records: Sequence[Mapping[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(dict(record), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            f.write("\n")


def _move_files(moves_dir: str | Path, *, pattern: str = "*.json") -> list[Path]:
    path = Path(moves_dir)
    if not path.exists():
        raise FileNotFoundError(f"moves directory does not exist: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"moves path is not a directory: {path}")
    return sorted(item for item in path.glob(pattern) if item.is_file())


def _player_from_path(path: Path) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in path.stem).strip("._-")
    return (cleaned or "invalid-file")[:80]


def _safe_player_filename(player: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in player).strip("._-")
    return (cleaned or "player")[:80]


def _invalid_command_for_file(path: Path, message: str) -> dict[str, Any]:
    return {
        "type": "invalid",
        "player": _player_from_path(path),
        "message": message,
        "reason": "invalid_move_json",
    }


def run_closed_match(
    transcript_path: str | Path,
    moves_dir: str | Path,
    *,
    pattern: str = "*.json",
    prior_quarantine_records: Iterable[Mapping[str, Any]] | None = None,
    min_player_interval_seconds: int = 0,
    season_scoring: bool = True,
    season: CompiledSeason | None = None,
    invalid_strikes_to_disqualify: int = 3,
) -> ClosedMatchResult:
    canonical_records = list(iter_jsonl(transcript_path)) if Path(transcript_path).exists() else []
    quarantine_records = (
        [dict(record) for record in prior_quarantine_records] if prior_quarantine_records is not None else []
    )
    decisions: list[GateDecision] = []

    for move_path in _move_files(moves_dir, pattern=pattern):
        try:
            command = load_move(move_path)
        except ValidationError as exc:
            command = _invalid_command_for_file(move_path, str(exc))
        decision = gate_move(
            canonical_records,
            quarantine_records,
            command,
            min_player_interval_seconds=min_player_interval_seconds,
            season_scoring=season_scoring,
            season=season,
            invalid_strikes_to_disqualify=invalid_strikes_to_disqualify,
        )
        decisions.append(decision)
        if decision.accepted and decision.canonical_command is not None:
            canonical_records.append(decision.canonical_command)
        elif decision.quarantine_record is not None:
            record = dict(decision.quarantine_record)
            record["move_file"] = str(move_path)
            quarantine_records.append(record)

    return ClosedMatchResult(
        canonical_records=canonical_records,
        quarantine_records=quarantine_records,
        decisions=decisions,
    )


def render_closed_match_markdown(result: ClosedMatchResult) -> str:
    lines = [
        "# Closed Match Round Report",
        "",
        f"Accepted moves: `{result.accepted_count}`",
        f"Rejected/quarantined moves: `{result.rejected_count}`",
        "",
        "| player | accepted | branch | reason | score_delta |",
        "| --- | ---: | --- | --- | ---: |",
    ]
    for decision in result.decisions:
        verdict = decision.verdict
        lines.append(
            f"| `{decision.player}` | {str(decision.accepted).lower()} | "
            f"`{decision.branch}` | `{decision.reason}` | {verdict.get('score_delta', 0)} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_closed_match_outputs(
    result: ClosedMatchResult,
    out_dir: str | Path,
    *,
    min_player_interval_seconds: int = 0,
    season_scoring: bool = True,
    season: CompiledSeason | None = None,
    reveal_policy: str = "redacted",
) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    canonical_path = out / "canonical.jsonl"
    quarantine_path = out / "quarantine.jsonl"
    decisions_path = out / "decisions.json"
    report_path = out / "round_report.md"
    standings_md_path = out / "standings.md"
    standings_json_path = out / "standings.json"
    frontier_md_path = out / "frontier.md"
    frontier_json_path = out / "frontier.json"
    observer_md_path = out / "observer_report.md"
    observer_html_path = out / "observer_report.html"
    evaluation_md_path = out / "season_eval.md"
    evaluation_json_path = out / "season_eval.json"
    brief_md_path = out / "agent_brief.md"
    brief_json_path = out / "agent_brief.json"

    _write_jsonl(canonical_path, result.canonical_records)
    _write_jsonl(quarantine_path, result.quarantine_records)
    _write_json(decisions_path, result.to_dict())
    report_path.write_text(render_closed_match_markdown(result), encoding="utf-8")

    replay_state = replay_records(
        result.canonical_records,
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
        season=season,
    )
    standings = build_season_standings(
        result.canonical_records,
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
        season=season,
    )
    standings_md_path.write_text(render_standings_markdown(standings), encoding="utf-8")
    _write_json(standings_json_path, standings.to_dict())

    frontier = build_frontier_report_from_records(
        result.canonical_records,
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
        season=season,
    )
    frontier_md_path.write_text(
        render_frontier_markdown(frontier, display_season_id=season.spec.season_id if season else None),
        encoding="utf-8",
    )
    _write_json(frontier_json_path, frontier.to_dict())

    observer_md_path.write_text(
        render_report(
            result.canonical_records,
            min_player_interval_seconds=min_player_interval_seconds,
            season_scoring=season_scoring,
            reveal_policy=reveal_policy,
            season=season,
        ),
        encoding="utf-8",
    )
    observer_html_path.write_text(
        render_html_report(
            result.canonical_records,
            min_player_interval_seconds=min_player_interval_seconds,
            season_scoring=season_scoring,
            reveal_policy=reveal_policy,
            season=season,
        ),
        encoding="utf-8",
    )

    evaluation = evaluate_records(
        result.canonical_records,
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
        season=season,
    )
    evaluation_md_path.write_text(render_evaluation_markdown(evaluation), encoding="utf-8")
    _write_json(evaluation_json_path, evaluation.to_dict())

    brief = build_agent_brief(standings)
    brief_md_path.write_text(render_agent_brief_markdown(brief), encoding="utf-8")
    _write_json(brief_json_path, brief)

    player_briefs_dir = out / "player_briefs"
    player_briefs_dir.mkdir(exist_ok=True)
    player_brief_index: dict[str, str] = {}
    for row in standings.leaderboard:
        player = str(row["player"])
        stem = _safe_player_filename(player)
        player_brief = build_agent_brief(
            standings,
            player=player,
            recent_verdicts=replay_state.verdicts,
        )
        md_name = f"{stem}.md"
        json_name = f"{stem}.json"
        (player_briefs_dir / md_name).write_text(render_agent_brief_markdown(player_brief), encoding="utf-8")
        _write_json(player_briefs_dir / json_name, player_brief)
        player_brief_index[player] = f"player_briefs/{md_name}"
    _write_json(player_briefs_dir / "index.json", player_brief_index)

    return {
        "canonical": str(canonical_path),
        "quarantine": str(quarantine_path),
        "decisions": str(decisions_path),
        "report": str(report_path),
        "standings": str(standings_md_path),
        "frontier": str(frontier_md_path),
        "frontier_json": str(frontier_json_path),
        "observer_report": str(observer_md_path),
        "observer_report_html": str(observer_html_path),
        "season_eval": str(evaluation_md_path),
        "season_eval_json": str(evaluation_json_path),
        "agent_brief": str(brief_md_path),
        "player_briefs": str(player_briefs_dir / "index.json"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Batch-evaluate a directory of closed-match JSON moves.")
    parser.add_argument("transcript", help="Starting canonical transcript JSONL")
    parser.add_argument("moves_dir", help="Directory containing participant JSON move files")
    parser.add_argument("--out", required=True, help="Output directory for round artifacts")
    parser.add_argument("--pattern", default="*.json", help="Move file glob within moves_dir")
    parser.add_argument("--prior-quarantine", help="Existing quarantine JSONL to carry invalid strikes forward")
    parser.add_argument("--min-player-interval-seconds", type=int, default=0)
    parser.add_argument("--no-season-scoring", action="store_true")
    parser.add_argument("--season", help="Optional data-only season spec path")
    parser.add_argument("--invalid-strikes-to-disqualify", type=int, default=3)
    parser.add_argument("--reveal-policy", choices=["full", "redacted"], default="redacted")
    parser.add_argument("--strict-exit", action="store_true", help="Return non-zero when any move is rejected.")
    args = parser.parse_args(argv)

    season = load_optional_compiled_season(args.season)
    prior_quarantine_records = iter_quarantine_jsonl(args.prior_quarantine) if args.prior_quarantine else None
    result = run_closed_match(
        args.transcript,
        args.moves_dir,
        pattern=args.pattern,
        prior_quarantine_records=prior_quarantine_records,
        min_player_interval_seconds=args.min_player_interval_seconds,
        season_scoring=not args.no_season_scoring,
        season=season,
        invalid_strikes_to_disqualify=args.invalid_strikes_to_disqualify,
    )
    outputs = write_closed_match_outputs(
        result,
        args.out,
        min_player_interval_seconds=args.min_player_interval_seconds,
        season_scoring=not args.no_season_scoring,
        season=season,
        reveal_policy=args.reveal_policy,
    )
    print(json.dumps({"result": result.to_dict(), "outputs": outputs}, ensure_ascii=False, indent=2, sort_keys=True))
    if args.strict_exit and result.rejected_count:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
