"""Deterministic local proxy for AI-player appeal.

This is not a claim that remote models will enjoy the game. It checks whether a
generated match pack exposes the machine-readable affordances, continuity, and
competitive pressure that make an AI-vs-AI round worth trying.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .external_trial import inspect_external_trial
from .packet_agent import choose_packet_move, load_packet
from .season_catalog import load_optional_compiled_season
from .submission_check import check_submission


@dataclass(frozen=True)
class AIAppealCheck:
    key: str
    passed: bool
    category: str
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "passed": self.passed,
            "category": self.category,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class AIAppealReport:
    pack_dir: str
    passed: bool
    score: str
    metrics: dict[str, Any]
    checks: list[AIAppealCheck]
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pack_dir": self.pack_dir,
            "passed": self.passed,
            "score": self.score,
            "metrics": self.metrics,
            "checks": [check.to_dict() for check in self.checks],
            "note": self.note,
        }


def _check(key: str, condition: bool, *, category: str, evidence: str) -> AIAppealCheck:
    return AIAppealCheck(key=key, passed=bool(condition), category=category, evidence=evidence)


def _load_json(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, f"missing {path.name}"
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON in {path.name}: {exc.msg}"


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _packet_paths(root: Path, manifest: dict[str, Any]) -> dict[str, Path]:
    packet_index = manifest.get("player_packets")
    if not isinstance(packet_index, dict):
        return {}
    paths: dict[str, Path] = {}
    for player, relative in packet_index.items():
        if not isinstance(player, str) or not isinstance(relative, str):
            continue
        path = root / relative
        if path.exists():
            paths[player] = path
    return paths


def _packet_structures_ok(packet_paths: dict[str, Path]) -> tuple[bool, str]:
    errors: list[str] = []
    for player, path in packet_paths.items():
        payload, error = _load_json(path)
        packet = _mapping(payload)
        if error:
            errors.append(f"{player}: {error}")
            continue
        if packet.get("schema") != "conjecture_golf.player_packet.v1":
            errors.append(f"{player}: unsupported packet schema")
        if _mapping(packet.get("identity_lock")).get("required_player") != player:
            errors.append(f"{player}: identity lock mismatch")
        if int(packet.get("candidate_count", 0) or 0) <= 0:
            errors.append(f"{player}: no candidate lanes")
    if errors:
        return False, "; ".join(errors[:6])
    return True, f"{len(packet_paths)} player packets with identity locks and candidate lanes."


def _validate_packet_moves(root: Path, manifest: dict[str, Any]) -> tuple[int, int, list[str]]:
    transcript = root / str(manifest.get("transcript", "transcript.jsonl"))
    season_name = manifest.get("season_spec")
    season_path = root / season_name if isinstance(season_name, str) and season_name else None
    season = load_optional_compiled_season(season_path)
    accepted = 0
    game_moves = 0
    errors: list[str] = []
    for player, packet_path in _packet_paths(root, manifest).items():
        try:
            move = choose_packet_move(load_packet(packet_path))
            report = check_submission(
                transcript,
                move,
                expected_player=player,
                season=season,
            )
        except Exception as exc:  # pragma: no cover - defensive report path
            errors.append(f"{player}: {exc}")
            continue
        if report["accepted"] is True:
            accepted += 1
        else:
            errors.append(f"{player}: {report['status']}")
        if move.get("type") in {"conjecture", "counterexample"}:
            game_moves += 1
    return accepted, game_moves, errors


def assess_match_pack_ai_appeal(
    pack_dir: str | Path,
    *,
    validate_packets: bool = False,
    min_participants: int = 2,
    min_strategic_roles: int = 2,
    min_candidate_lanes: int = 8,
    min_open_frontier_lanes: int = 4,
    min_moves_remaining: int = 8,
) -> AIAppealReport:
    root = Path(pack_dir)
    checks: list[AIAppealCheck] = []
    metrics: dict[str, Any] = {}

    root_exists = root.exists() and root.is_dir()
    checks.append(
        _check(
            "match_pack_directory_exists",
            root_exists,
            category="structure",
            evidence=f"match pack directory: {root}",
        )
    )
    if not root_exists:
        return AIAppealReport(
            pack_dir=str(root),
            passed=False,
            score="0/1",
            metrics=metrics,
            checks=checks,
            note="Local structural proxy only; real appeal still requires external AI play.",
        )

    manifest_raw, manifest_error = _load_json(root / "manifest.json")
    ai_state_raw, ai_state_error = _load_json(root / "AI_STATE.json")
    candidates_raw, candidates_error = _load_json(root / "MOVE_CANDIDATES.json")
    manifest = _mapping(manifest_raw)
    ai_state = _mapping(ai_state_raw)
    candidates = _mapping(candidates_raw)

    checks.append(
        _check(
            "machine_json_surfaces_parse",
            not any([manifest_error, ai_state_error, candidates_error]),
            category="machine_playability",
            evidence="manifest, AI_STATE, and MOVE_CANDIDATES parse"
            if not any([manifest_error, ai_state_error, candidates_error])
            else "; ".join(error for error in [manifest_error, ai_state_error, candidates_error] if error),
        )
    )
    checks.append(
        _check(
            "machine_surfaces_have_expected_schemas",
            ai_state.get("schema") == "conjecture_golf.ai_state.v1"
            and ai_state.get("audience") == "machine_player"
            and candidates.get("schema") == "conjecture_golf.move_candidates.v1"
            and candidates.get("audience") == "machine_player",
            category="machine_playability",
            evidence="AI_STATE and MOVE_CANDIDATES are machine-player payloads.",
        )
    )

    season = _mapping(ai_state.get("season"))
    moves_remaining = int(season.get("moves_remaining", 0) or 0)
    complete = bool(season.get("complete", True))
    next_objectives = _list(ai_state.get("next_objectives"))
    metrics.update(
        {
            "moves_remaining": moves_remaining,
            "season_complete": complete,
            "next_objectives": len(next_objectives),
        }
    )
    checks.append(
        _check(
            "season_has_continuation_pressure",
            not complete and moves_remaining >= min_moves_remaining and bool(next_objectives),
            category="continuity",
            evidence=f"{moves_remaining} moves remaining, {len(next_objectives)} next objectives.",
        )
    )

    frontier_rows = [row for row in _list(ai_state.get("frontier_tensor")) if isinstance(row, dict)]
    open_rows = [row for row in frontier_rows if int(row.get("open", 0) or 0) > 0]
    open_obligations = sum(int(row.get("open", 0) or 0) for row in open_rows)
    metrics.update(
        {
            "frontier_rows": len(frontier_rows),
            "open_frontier_lanes": len(open_rows),
            "open_obligations": open_obligations,
        }
    )
    checks.append(
        _check(
            "frontier_has_unclaimed_machine_targets",
            len(open_rows) >= min_open_frontier_lanes and open_obligations > 0,
            category="continuity",
            evidence=f"{len(open_rows)} open frontier lanes, {open_obligations} open obligations.",
        )
    )

    title_races = [race for race in _list(ai_state.get("title_races")) if isinstance(race, dict)]
    led_races = [race for race in title_races if race.get("leader") is not None]
    title_leaders = sorted({str(race["leader"]) for race in led_races if race.get("leader") is not None})
    metrics.update(
        {
            "title_races": len(title_races),
            "led_title_races": len(led_races),
            "distinct_title_leaders": len(title_leaders),
        }
    )
    checks.append(
        _check(
            "competitive_titles_are_live",
            len(title_races) >= 5 and len(led_races) >= 4 and len(title_leaders) >= 2,
            category="competition",
            evidence=f"{len(led_races)} led title races with {len(title_leaders)} distinct leaders.",
        )
    )

    candidate_rows = [candidate for candidate in _list(candidates.get("candidates")) if isinstance(candidate, dict)]
    candidate_kinds = sorted({str(candidate.get("kind")) for candidate in candidate_rows if candidate.get("kind")})
    candidate_lanes = sorted({str(candidate.get("lane")) for candidate in candidate_rows if candidate.get("lane")})
    metrics.update(
        {
            "candidate_count": int(candidates.get("candidate_count", len(candidate_rows)) or 0),
            "candidate_kinds": candidate_kinds,
            "candidate_lanes": candidate_lanes,
        }
    )
    checks.append(
        _check(
            "candidate_lanes_are_diverse",
            len(candidate_rows) >= min_candidate_lanes
            and "conjecture_seed" in candidate_kinds
            and "score_lane" in candidate_kinds
            and len(candidate_lanes) >= 3,
            category="machine_playability",
            evidence=f"{len(candidate_rows)} candidates, kinds={candidate_kinds}, lanes={candidate_lanes}.",
        )
    )

    hard_constraints = _list(candidates.get("hard_constraints"))
    checks.append(
        _check(
            "output_contract_is_machine_enforced",
            "unknown fields are invalid" in hard_constraints
            and any("exactly one JSON object" in str(item) for item in hard_constraints),
            category="safety",
            evidence="candidate payload repeats JSON-only and unknown-field constraints.",
        )
    )

    stale_traps = _list(ai_state.get("stale_traps"))
    checks.append(
        _check(
            "stale_pressure_is_visible",
            bool(stale_traps),
            category="competition",
            evidence=f"{len(stale_traps)} stale trap rows exposed to agents.",
        )
    )
    metrics["stale_traps"] = len(stale_traps)

    participant_strategies = manifest.get("participant_strategies")
    if not isinstance(participant_strategies, dict):
        participant_strategies = {}
    strategic_roles = sorted({str(role) for role in participant_strategies.values() if str(role)})
    packet_paths = _packet_paths(root, manifest)
    packet_structures_ok, packet_evidence = _packet_structures_ok(packet_paths)
    metrics.update(
        {
            "participants": len(participant_strategies),
            "strategic_roles": strategic_roles,
            "player_packets": len(packet_paths),
        }
    )
    checks.append(
        _check(
            "participant_roles_support_various_ai_players",
            len(participant_strategies) >= min_participants and len(strategic_roles) >= min_strategic_roles,
            category="multi_agent",
            evidence=f"{len(participant_strategies)} participants, roles={strategic_roles}.",
        )
    )
    checks.append(
        _check(
            "player_packets_lock_identity_and_candidates",
            len(packet_paths) == len(participant_strategies) and packet_structures_ok,
            category="machine_playability",
            evidence=packet_evidence
            if len(packet_paths) == len(participant_strategies)
            else f"{len(packet_paths)} packets for {len(participant_strategies)} participants.",
        )
    )

    if validate_packets:
        accepted, game_moves, errors = _validate_packet_moves(root, manifest)
        metrics.update({"packet_moves_accepted": accepted, "packet_game_moves": game_moves})
        checks.append(
            _check(
                "packet_moves_are_locally_checkable",
                not errors and accepted == len(packet_paths) and game_moves == len(packet_paths) and accepted > 0,
                category="machine_playability",
                evidence=f"{accepted}/{len(packet_paths)} packet moves accepted as game moves."
                if not errors
                else "; ".join(errors[:6]),
            )
        )

    trial_report = inspect_external_trial(root)
    metrics["external_trial_preflight_passed"] = trial_report.passed
    checks.append(
        _check(
            "external_trial_preflight_passes",
            trial_report.passed,
            category="external_ai_trial",
            evidence="external_trial kit is ready before sending prompts."
            if trial_report.passed
            else "external_trial preflight failed; run season0 trial-preflight for details.",
        )
    )

    passed_checks = sum(1 for check in checks if check.passed)
    passed = passed_checks == len(checks)
    return AIAppealReport(
        pack_dir=str(root),
        passed=passed,
        score=f"{passed_checks}/{len(checks)}",
        metrics=metrics,
        checks=checks,
        note=(
            "This is a deterministic local proxy for AI appeal. It proves machine affordances, "
            "continuity, and competitive pressure in the pack; it does not prove that remote models "
            "actually enjoyed the game."
        ),
    )


def render_ai_appeal_markdown(report: AIAppealReport) -> str:
    lines = [
        "# AI Appeal Audit",
        "",
        f"Passed: `{str(report.passed).lower()}`",
        f"Score: `{report.score}`",
        f"Match pack: `{report.pack_dir}`",
        "",
        report.note,
        "",
        "## Metrics",
        "",
        "| metric | value |",
        "| --- | --- |",
    ]
    for key, value in sorted(report.metrics.items()):
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (list, dict)) else str(value)
        lines.append(f"| `{key}` | `{rendered}` |")
    lines.extend(
        [
            "",
            "## Checks",
            "",
            "| check | category | passed | evidence |",
            "| --- | --- | ---: | --- |",
        ]
    )
    for check in report.checks:
        lines.append(f"| `{check.key}` | {check.category} | {str(check.passed).lower()} | {check.evidence} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit a match pack as a local proxy for AI-player appeal.")
    parser.add_argument("match_pack", help="Generated match-pack directory")
    parser.add_argument(
        "--validate-packets",
        action="store_true",
        help="Run packet_agent plus submission_check for every player packet.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    args = parser.parse_args(argv)

    report = assess_match_pack_ai_appeal(args.match_pack, validate_packets=args.validate_packets)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_ai_appeal_markdown(report))
    return 0 if report.passed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
