"""Machine-oriented state surfaces for AI Conjecture Golf players."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from .frontier import FrontierReport, build_frontier_report
from .replay import ReplayState, iter_jsonl, replay_records
from .season_catalog import load_optional_compiled_season
from .season_engine import CompiledSeason
from .season_standings import SeasonStandings, build_season_standings


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _transition_parts(transition: str) -> tuple[str | None, str | None]:
    if "->" not in transition:
        return None, None
    before, after = transition.split("->", 1)
    return before, after


def _safe_conjecture_token(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in value.strip())
    return cleaned.strip("._-") or "player"


def _frontier_tensor(frontier: FrontierReport) -> list[dict[str, Any]]:
    uncovered = frontier.uncovered_summary.get("by_claim_and_transition", {})
    covered = frontier.covered_summary.get("by_claim_and_transition", {})
    if not isinstance(uncovered, Mapping) or not isinstance(covered, Mapping):
        return []
    keys = sorted(set(uncovered) | set(covered))
    rows = []
    for key in keys:
        claim_kind, transition = str(key).split(":", 1)
        open_count = int(uncovered.get(key, 0))
        covered_count = int(covered.get(key, 0))
        total = open_count + covered_count
        rows.append(
            {
                "claim_kind": claim_kind,
                "transition": transition,
                "covered": covered_count,
                "open": open_count,
                "total": total,
                "open_ratio": round(open_count / total, 6) if total else 0.0,
            }
        )
    return rows


def _player_vectors(standings: SeasonStandings) -> list[dict[str, Any]]:
    vectors = []
    for rank, row in enumerate(standings.leaderboard, start=1):
        vectors.append(
            {
                "rank": rank,
                "player": row["player"],
                "total": int(row.get("total", 0)),
                "law_score": int(row.get("law_score", 0)),
                "counterexample_score": int(row.get("counterexample_score", 0)),
                "invalid_penalty": int(row.get("invalid_penalty", 0)),
                "valid_conjectures": int(row.get("valid_conjectures", 0)),
                "valid_counterexamples": int(row.get("valid_counterexamples", 0)),
                "invalid_moves": int(row.get("invalid_moves", 0)),
                "new_obligations": int(row.get("new_obligations", 0)),
                "necessary_obligations": int(row.get("necessary_obligations", 0)),
                "novel_counterexamples": int(row.get("novel_counterexamples", 0)),
                "stale_or_duplicate_moves": int(row.get("stale_or_duplicate_moves", 0)),
            }
        )
    return vectors


def _verdict_name(verdict: Any) -> str | None:
    details = getattr(verdict, "details", None)
    if not isinstance(details, Mapping):
        return None
    name = details.get("name")
    return name if isinstance(name, str) and name else None


def _conjecture_index(state: ReplayState) -> list[dict[str, Any]]:
    status_by_name: dict[str, dict[str, Any]] = {}
    for verdict in state.verdicts:
        if getattr(verdict, "kind", None) != "conjecture":
            continue
        name = _verdict_name(verdict)
        if name is None:
            continue
        details = getattr(verdict, "details", None) or {}
        ok = bool(getattr(verdict, "ok", False))
        if ok:
            status = "accepted_law"
        elif name in state.countered_conjectures:
            status = "countered_target"
        elif name in state.conjectures:
            status = "open_refutation_target"
        else:
            status = "rejected_or_invalid"
        status_by_name[name] = {
            "name": name,
            "player": getattr(verdict, "player", None),
            "status": status,
            "ok": ok,
            "claim_kind": details.get("claim_kind"),
            "score_delta": int(getattr(verdict, "score_delta", 0)),
            "target_value": int(details.get("season_target_value", 0) or 0),
            "new_obligations": int(details.get("season_new_obligations", 0) or 0),
            "potential_obligations": int(details.get("season_potential_obligations", 0) or 0),
            "counterexample_digest": _digest(details["counterexample"])
            if isinstance(details.get("counterexample"), Mapping)
            else None,
        }
    rows = []
    for name, conjecture in sorted(state.conjectures.items()):
        row = status_by_name.get(name, {"name": name, "status": "known_conjecture"})
        rows.append(
            {
                **row,
                "conditions": len(conjecture.get("if", [])) if isinstance(conjecture.get("if"), list) else 0,
                "target_becomes": (
                    conjecture.get("then", {}).get("target_becomes")
                    if isinstance(conjecture.get("then"), Mapping)
                    else None
                ),
            }
        )
    return rows


def _open_refutation_targets(state: ReplayState) -> list[dict[str, Any]]:
    targets = []
    for row in _conjecture_index(state):
        if row["status"] != "open_refutation_target":
            continue
        targets.append(
            {
                "name": row["name"],
                "player": row.get("player"),
                "claim_kind": row.get("claim_kind"),
                "target_value": row.get("target_value", 0),
                "potential_obligations": row.get("potential_obligations", 0),
                "counterexample_digest": row.get("counterexample_digest"),
            }
        )
    return sorted(targets, key=lambda row: (-int(row["target_value"]), row["name"]))


def build_ai_state(
    records: Iterable[Mapping[str, Any]],
    *,
    replay_state: ReplayState | None = None,
    standings: SeasonStandings | None = None,
    frontier: FrontierReport | None = None,
    season: CompiledSeason | None = None,
    min_player_interval_seconds: int = 0,
    season_scoring: bool = True,
    participants: list[Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """Build a compact machine-readable state map for player agents."""

    records = [dict(record) for record in records]
    state = replay_state or replay_records(
        records,
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
        season=season,
    )
    standings = standings or build_season_standings(
        records,
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
        season=season,
    )
    frontier = frontier or build_frontier_report(state, season=season)
    standings_data = standings.to_dict()
    return {
        "schema": "conjecture_golf.ai_state.v1",
        "audience": "machine_player",
        "transcript_digest": _digest(records),
        "transcript_records": len(records),
        "season": {
            "id": standings.season_id,
            "phase": standings.phase,
            "move_cap": standings.move_cap,
            "moves_played": standings.total_moves,
            "moves_remaining": standings.moves_remaining,
            "complete": standings.season_complete,
            "coverage_target_ratio": standings.coverage_target_ratio,
        },
        "protocol": {
            "command_types": ["hello", "conjecture", "counterexample", "score"],
            "claim_kinds": ["sufficient", "necessary", "equivalence"],
            "symbols": [".", "F", "W", "S"],
            "relations": ["orthogonal", "diagonal", "king"],
            "condition_ops": ["target_is", "exists", "not_exists", "count_at_least", "count_exactly"],
            "output_contract": "exactly_one_json_object_no_prose",
        },
        "participants": [dict(item) for item in participants or []],
        "player_vectors": _player_vectors(standings),
        "title_races": [
            {
                "key": race["key"],
                "leader": race["leader"],
                "value": race["value"],
                "contenders": race["contenders"],
            }
            for race in standings_data["title_races"]
        ],
        "frontier_tensor": _frontier_tensor(frontier),
        "open_refutation_targets": _open_refutation_targets(state),
        "conjecture_index": _conjecture_index(state),
        "next_objectives": list(standings.next_objectives),
        "stale_traps": list(frontier.stale_traps),
        "source_files": {
            "transcript": "transcript.jsonl",
            "standings": "standings.json",
            "frontier": "frontier.json",
            "move_candidates": "MOVE_CANDIDATES.json",
        },
    }


def _frontier_candidates(ai_state: Mapping[str, Any], *, limit: int = 8) -> list[dict[str, Any]]:
    rows = sorted(
        ai_state.get("frontier_tensor", []),
        key=lambda row: (-int(row.get("open", 0)), row.get("claim_kind", ""), row.get("transition", "")),
    )
    candidates = []
    for row in rows[:limit]:
        before, after = _transition_parts(str(row["transition"]))
        candidates.append(
            {
                "id": f"frontier:{row['claim_kind']}:{row['transition']}",
                "kind": "conjecture_seed",
                "lane": "frontier",
                "priority": int(row["open"]),
                "claim_kind": row["claim_kind"],
                "transition": row["transition"],
                "move_seed": {
                    "type": "conjecture",
                    "player": "your-agent-name",
                    "name": f"your_agent_name_{row['claim_kind']}_{str(row['transition']).replace('->', '_to_')}",
                    "claim_kind": row["claim_kind"],
                    "if": [{"target_is": before}] if before is not None else [],
                    "then": {"target_becomes": after},
                },
                "agent_fill_required": [
                    "replace your-agent-name",
                    "add enough local conditions to make the conjecture true and non-vacuous",
                    "verify with submission_check before returning",
                ],
            }
        )
    return candidates


def _counterexample_candidates(ai_state: Mapping[str, Any], *, limit: int = 6) -> list[dict[str, Any]]:
    candidates = []
    for target in list(ai_state.get("open_refutation_targets", []))[:limit]:
        candidates.append(
            {
                "id": f"refute:{target['name']}",
                "kind": "counterexample_hunt",
                "lane": "refuter",
                "priority": int(target.get("target_value", 0)),
                "against": target["name"],
                "counterexample_digest": target.get("counterexample_digest"),
                "move_seed": {
                    "type": "counterexample",
                    "player": "your-agent-name",
                    "against": target["name"],
                    "before": [".....", ".....", ".....", ".....", "....."],
                },
                "agent_fill_required": [
                    "replace your-agent-name",
                    "replace before with a real board that falsifies the target",
                    "prefer a witness different from the verifier-revealed digest",
                ],
            }
        )
    return candidates


def _title_candidates(ai_state: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates = []
    for race in ai_state.get("title_races", []):
        if race.get("leader") is None:
            continue
        candidates.append(
            {
                "id": f"title:{race['key']}",
                "kind": "score_lane",
                "lane": race["key"],
                "priority": int(race.get("value") or 0),
                "leader": race["leader"],
                "contenders": race.get("contenders", []),
            }
        )
    return candidates


def build_move_candidates(ai_state: Mapping[str, Any]) -> dict[str, Any]:
    """Build machine-readable candidate lanes from an AI state map."""

    candidates = _frontier_candidates(ai_state) + _counterexample_candidates(ai_state) + _title_candidates(ai_state)
    return {
        "schema": "conjecture_golf.move_candidates.v1",
        "audience": "machine_player",
        "transcript_digest": ai_state["transcript_digest"],
        "candidate_count": len(candidates),
        "candidates": candidates,
        "hard_constraints": [
            "return exactly one JSON object",
            "do not include prose or Markdown fences",
            "do not edit verifier or source files for score",
            "unknown fields are invalid",
        ],
    }


def _candidate_for_player(candidate: Mapping[str, Any], player: str) -> dict[str, Any]:
    prepared = dict(candidate)
    move_seed = prepared.get("move_seed")
    if isinstance(move_seed, Mapping):
        move = dict(move_seed)
        move["player"] = player
        if isinstance(move.get("name"), str):
            move["name"] = move["name"].replace("your_agent_name", _safe_conjecture_token(player))
        prepared["move_seed"] = move
    return prepared


def build_player_packet(
    ai_state: Mapping[str, Any],
    move_candidates: Mapping[str, Any],
    *,
    player: str,
    strategy: str | None = None,
) -> dict[str, Any]:
    """Build one machine-readable turn packet for a specific player."""

    player_vector = next(
        (row for row in ai_state.get("player_vectors", []) if row.get("player") == player),
        None,
    )
    candidate_lanes = [
        _candidate_for_player(candidate, player)
        for candidate in move_candidates.get("candidates", [])
    ]
    return {
        "schema": "conjecture_golf.player_packet.v1",
        "audience": "machine_player",
        "player": player,
        "strategy": strategy,
        "transcript_digest": ai_state["transcript_digest"],
        "identity_lock": {
            "required_player": player,
            "move_json_must_contain": {"player": player},
        },
        "season": ai_state["season"],
        "player_vector": player_vector,
        "candidate_lanes": candidate_lanes,
        "candidate_count": len(candidate_lanes),
        "stale_traps": list(ai_state.get("stale_traps", [])),
        "hard_constraints": list(move_candidates.get("hard_constraints", [])),
        "source_files": {
            "ai_state": "AI_STATE.json",
            "move_candidates": "MOVE_CANDIDATES.json",
            "transcript": "transcript.jsonl",
        },
        "output_contract": {
            "format": "exactly_one_json_object",
            "no_prose": True,
            "allowed_command_types": ai_state.get("protocol", {}).get("command_types", []),
        },
    }


def build_ai_state_bundle(
    records: Iterable[Mapping[str, Any]],
    *,
    replay_state: ReplayState | None = None,
    standings: SeasonStandings | None = None,
    frontier: FrontierReport | None = None,
    season: CompiledSeason | None = None,
    min_player_interval_seconds: int = 0,
    season_scoring: bool = True,
    participants: list[Mapping[str, str]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    ai_state = build_ai_state(
        records,
        replay_state=replay_state,
        standings=standings,
        frontier=frontier,
        season=season,
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
        participants=participants,
    )
    return ai_state, build_move_candidates(ai_state)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render machine-oriented Conjecture Golf AI state.")
    parser.add_argument("transcript", help="Transcript JSONL path")
    parser.add_argument("--season", help="Optional data-only season spec path")
    parser.add_argument("--candidates", action="store_true", help="Print MOVE_CANDIDATES payload instead of AI_STATE.")
    args = parser.parse_args(argv)

    season = load_optional_compiled_season(args.season)
    records = list(iter_jsonl(args.transcript))
    ai_state, move_candidates = build_ai_state_bundle(records, season=season)
    payload = move_candidates if args.candidates else ai_state
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
