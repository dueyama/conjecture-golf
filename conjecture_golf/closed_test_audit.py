"""Deterministic audit for closed multi-agent Season 0 tests."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .replay import ReplayState, iter_jsonl, replay_records
from .score import leaderboard_rows
from .season_catalog import load_optional_compiled_season
from .season_engine import CompiledSeason
from .season_eval import style_notes_by_player
from .season_standings import SeasonStandings, build_season_standings_from_state


@dataclass(frozen=True)
class ClosedTestCheck:
    key: str
    passed: bool
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "passed": self.passed,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class ClosedTestAudit:
    passed: bool
    checks: list[ClosedTestCheck]
    summary: dict[str, Any]
    next_steps: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [check.to_dict() for check in self.checks],
            "summary": self.summary,
            "next_steps": self.next_steps,
        }


def _check(key: str, condition: bool, evidence: str) -> ClosedTestCheck:
    return ClosedTestCheck(key=key, passed=bool(condition), evidence=evidence)


def _game_move_count(verdicts: Iterable[Any]) -> int:
    return sum(1 for verdict in verdicts if verdict.kind in {"conjecture", "counterexample"})


def _has_original_counterexample(verdicts: Iterable[Any]) -> bool:
    return any(
        verdict.kind == "counterexample"
        and verdict.ok
        and (verdict.details or {}).get("season_score_basis") == "novel_first_counterexample"
        for verdict in verdicts
    )


def _has_characterization(verdicts: Iterable[Any]) -> bool:
    return any(
        verdict.kind == "conjecture"
        and verdict.ok
        and (verdict.details or {}).get("claim_kind") in {"necessary", "equivalence"}
        for verdict in verdicts
    )


def _strategic_styles(verdicts: Iterable[Any]) -> list[str]:
    styles: set[str] = set()
    for verdict in verdicts:
        details = verdict.details or {}
        if verdict.kind == "conjecture" and verdict.ok:
            claim_kind = details.get("claim_kind", "sufficient")
            if claim_kind == "equivalence":
                styles.add("equivalence_characterization")
            elif claim_kind == "necessary":
                styles.add("necessary_condition")
            else:
                styles.add("sufficient_law")
        if verdict.kind == "conjecture" and not verdict.ok:
            styles.add("risky_generalization")
        if verdict.kind == "counterexample" and verdict.ok:
            styles.add("counterexample_hunting")
        if details.get("season_score_basis") in {"stale_true_conjecture", "duplicate_conjecture", "duplicate_witness"}:
            styles.add("stale_or_duplicate_pressure")
    return sorted(styles)


def _next_steps(failed: list[str]) -> list[str]:
    if not failed:
        return [
            "Run the same protocol with external AI participants.",
            "Keep the transcript and generated match packs as public evidence.",
        ]
    advice = {
        "enough_players": "Invite more distinct participants before judging appeal.",
        "enough_game_moves": "Run another round; one round is too shallow for continuity.",
        "has_valid_law": "Improve player brief/frontier hints so agents can find true laws.",
        "has_valid_counterexample": "Seed or permit broad false conjectures so refuters have targets.",
        "has_risky_generalization": "Include at least one aggressive participant or prompt variant.",
        "has_characterization_claim": "Prompt one participant to chase necessary/equivalence claims.",
        "has_original_counterexample": "Ask refuters to avoid verifier-revealed witnesses and seek original boards.",
        "has_stale_or_duplicate_pressure": "Run enough rounds for stale/duplicate penalties to become visible.",
        "has_distinct_styles": "Diversify prompts or participant model families; the styles are converging.",
        "has_live_title_races": "Tune move cap or participant mix so multiple titles remain live.",
        "has_next_objectives": "Regenerate frontier/standings; agents need visible next targets.",
        "season_not_exhausted": "Start a fresh season or larger candidate world before continuing.",
    }
    return [advice[key] for key in failed if key in advice]


def audit_records(
    records: Iterable[Mapping[str, Any]],
    *,
    season: CompiledSeason | None = None,
    min_players: int = 4,
    min_game_moves: int = 8,
    min_strategic_styles: int = 3,
    move_cap: int = 24,
) -> ClosedTestAudit:
    records = [dict(record) for record in records]
    state = replay_records(records, season_scoring=True, season=season)
    standings = build_season_standings_from_state(state, season=season, move_cap=move_cap)
    return audit_state(
        state,
        standings=standings,
        min_players=min_players,
        min_game_moves=min_game_moves,
        min_strategic_styles=min_strategic_styles,
    )


def audit_state(
    state: ReplayState,
    *,
    standings: SeasonStandings | None = None,
    season: CompiledSeason | None = None,
    min_players: int = 4,
    min_game_moves: int = 8,
    min_strategic_styles: int = 3,
    move_cap: int = 24,
) -> ClosedTestAudit:
    if standings is None:
        standings = build_season_standings_from_state(state, season=season, move_cap=move_cap)
    verdicts = state.verdicts
    rows = leaderboard_rows(state.scores)
    standings_data = standings.to_dict()
    players = sorted(state.scores)
    score_values = [int(row["total"]) for row in rows]
    strategic_styles = _strategic_styles(verdicts)
    style_notes = style_notes_by_player(verdicts)
    game_moves = _game_move_count(verdicts)
    valid_conjectures = sum(1 for verdict in verdicts if verdict.kind == "conjecture" and verdict.ok)
    valid_counterexamples = sum(1 for verdict in verdicts if verdict.kind == "counterexample" and verdict.ok)
    stale_moves = sum(
        1
        for verdict in verdicts
        if (verdict.details or {}).get("season_score_basis") in {"stale_true_conjecture", "already_countered"}
    )
    duplicate_moves = sum(
        1
        for verdict in verdicts
        if (verdict.details or {}).get("reason") == "duplicate_conjecture"
        or (verdict.details or {}).get("season_score_basis") == "duplicate_witness"
    )
    led_title_races = [race for race in standings_data["title_races"] if race["leader"]]
    distinct_title_leaders = {race["leader"] for race in led_title_races}

    checks = [
        _check(
            "enough_players",
            len(players) >= min_players,
            f"{len(players)} players; required {min_players}.",
        ),
        _check(
            "enough_game_moves",
            game_moves >= min_game_moves,
            f"{game_moves} conjecture/counterexample moves; required {min_game_moves}.",
        ),
        _check(
            "has_valid_law",
            valid_conjectures > 0,
            f"{valid_conjectures} accepted true conjectures.",
        ),
        _check(
            "has_valid_counterexample",
            valid_counterexamples > 0,
            f"{valid_counterexamples} accepted counterexamples.",
        ),
        _check(
            "has_risky_generalization",
            "risky_generalization" in strategic_styles,
            f"styles={strategic_styles}.",
        ),
        _check(
            "has_characterization_claim",
            _has_characterization(verdicts),
            "At least one accepted necessary or equivalence claim is present.",
        ),
        _check(
            "has_original_counterexample",
            _has_original_counterexample(verdicts),
            "At least one novel first counterexample is present.",
        ),
        _check(
            "has_stale_or_duplicate_pressure",
            stale_moves > 0 or duplicate_moves > 0,
            f"stale={stale_moves}, duplicate={duplicate_moves}.",
        ),
        _check(
            "has_distinct_styles",
            len(strategic_styles) >= min_strategic_styles,
            f"{len(strategic_styles)} styles; required {min_strategic_styles}.",
        ),
        _check(
            "has_live_title_races",
            len(led_title_races) >= 4 and len(distinct_title_leaders) >= 3,
            f"{len(led_title_races)} led title races, {len(distinct_title_leaders)} distinct leaders.",
        ),
        _check(
            "has_next_objectives",
            bool(standings.next_objectives),
            f"{len(standings.next_objectives)} next objectives.",
        ),
        _check(
            "season_not_exhausted",
            not standings.season_complete
            and standings_data["frontier"]["coverage_ratio"] < standings_data["coverage_target_ratio"],
            (
                f"moves_remaining={standings.moves_remaining}, "
                f"coverage={standings_data['frontier']['coverage_ratio']:.6f}."
            ),
        ),
    ]
    failed = [check.key for check in checks if not check.passed]
    summary = {
        "players": players,
        "total_moves": len(verdicts),
        "game_moves": game_moves,
        "strategic_styles": strategic_styles,
        "style_notes_by_player": style_notes,
        "score_spread": max(score_values) - min(score_values) if score_values else 0,
        "moves_remaining": standings.moves_remaining,
        "frontier_coverage_ratio": standings_data["frontier"]["coverage_ratio"],
    }
    return ClosedTestAudit(
        passed=not failed,
        checks=checks,
        summary=summary,
        next_steps=_next_steps(failed),
    )


def render_audit_markdown(audit: ClosedTestAudit) -> str:
    data = audit.to_dict()
    lines = [
        "# Closed Test Audit",
        "",
        f"Passed: `{str(data['passed']).lower()}`",
        "",
        "| check | passed | evidence |",
        "| --- | ---: | --- |",
    ]
    for check in data["checks"]:
        lines.append(f"| `{check['key']}` | {str(check['passed']).lower()} | {check['evidence']} |")
    lines.extend(["", "## Summary", ""])
    summary = data["summary"]
    lines.append(f"- Players: `{len(summary['players'])}`")
    lines.append(f"- Game moves: `{summary['game_moves']}`")
    lines.append(f"- Strategic styles: `{', '.join(summary['strategic_styles'])}`")
    lines.append(f"- Score spread: `{summary['score_spread']}`")
    lines.append(f"- Moves remaining: `{summary['moves_remaining']}`")
    lines.extend(["", "## Next Steps", ""])
    for step in data["next_steps"]:
        lines.append(f"- {step}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit whether a closed Season 0 test showed enough play depth.")
    parser.add_argument("path", help="Transcript JSONL path")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    parser.add_argument("--season", help="Optional data-only season spec path")
    parser.add_argument("--min-players", type=int, default=4)
    parser.add_argument("--min-game-moves", type=int, default=8)
    parser.add_argument("--min-strategic-styles", type=int, default=3)
    parser.add_argument("--move-cap", type=int, default=24)
    args = parser.parse_args(argv)

    audit = audit_records(
        iter_jsonl(args.path),
        season=load_optional_compiled_season(args.season),
        min_players=args.min_players,
        min_game_moves=args.min_game_moves,
        min_strategic_styles=args.min_strategic_styles,
        move_cap=args.move_cap,
    )
    if args.json:
        print(json.dumps(audit.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_audit_markdown(audit))
    return 0 if audit.passed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
