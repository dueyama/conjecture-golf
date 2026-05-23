"""Deterministic baseline player for machine player packets.

This is not an external AI. It is a local smoke-test agent that proves a
``player_packets/<player>.json`` file contains enough machine-readable state to
produce one valid move without reading the human guides.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .world import ValidationError


SAFE_CONJECTURE_LIBRARY: list[dict[str, Any]] = [
    {
        "key": "stone_persists",
        "claim_kind": "sufficient",
        "transition": "S->S",
        "if": [{"target_is": "S"}],
        "then": {"target_becomes": "S"},
    },
    {
        "key": "stone_persists_no_flowers",
        "claim_kind": "sufficient",
        "transition": "S->S",
        "if": [
            {"target_is": "S"},
            {"not_exists": {"symbol": "F", "relation": "king"}},
        ],
        "then": {"target_becomes": "S"},
    },
    {
        "key": "stone_is_necessary_for_stone",
        "claim_kind": "necessary",
        "transition": "S->S",
        "if": [{"target_is": "S"}],
        "then": {"target_becomes": "S"},
    },
    {
        "key": "water_with_escape_persists",
        "claim_kind": "sufficient",
        "transition": "W->W",
        "if": [
            {"target_is": "W"},
            {"exists": {"symbol": ".", "relation": "orthogonal"}},
        ],
        "then": {"target_becomes": "W"},
    },
    {
        "key": "flower_wither_from_two_stones",
        "claim_kind": "sufficient",
        "transition": "F->.",
        "if": [
            {"target_is": "F"},
            {"count_at_least": {"symbol": "S", "relation": "king", "n": 2}},
        ],
        "then": {"target_becomes": "."},
    },
    {
        "key": "water_spreads_without_diagonal_blockers",
        "claim_kind": "sufficient",
        "transition": ".->W",
        "if": [
            {"target_is": "."},
            {"count_exactly": {"symbol": "W", "relation": "orthogonal", "n": 2}},
            {"not_exists": {"symbol": "S", "relation": "diagonal"}},
            {"not_exists": {"symbol": "W", "relation": "diagonal"}},
        ],
        "then": {"target_becomes": "W"},
    },
]


def _safe_conjecture_token(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in value.strip())
    return cleaned.strip("._-") or "player"


def load_packet(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValidationError("player packet must be a JSON object")
    if payload.get("schema") != "conjecture_golf.player_packet.v1":
        raise ValidationError("unsupported player packet schema")
    return payload


def _required_player(packet: Mapping[str, Any]) -> str:
    identity = packet.get("identity_lock")
    player = identity.get("required_player") if isinstance(identity, Mapping) else packet.get("player")
    if not isinstance(player, str) or not player.strip():
        raise ValidationError("player packet is missing required player")
    return player.strip()


def _candidate_priorities(packet: Mapping[str, Any]) -> dict[tuple[str, str], int]:
    priorities: dict[tuple[str, str], int] = {}
    for candidate in packet.get("candidate_lanes", []):
        if not isinstance(candidate, Mapping) or candidate.get("kind") != "conjecture_seed":
            continue
        claim_kind = candidate.get("claim_kind")
        transition = candidate.get("transition")
        if isinstance(claim_kind, str) and isinstance(transition, str):
            priorities[(claim_kind, transition)] = max(
                priorities.get((claim_kind, transition), 0),
                int(candidate.get("priority", 0) or 0),
            )
    for row in packet.get("stale_traps", []):
        if not isinstance(row, Mapping):
            continue
        claim_kind = row.get("claim_kind")
        transition = row.get("transition")
        if isinstance(claim_kind, str) and isinstance(transition, str):
            priorities[(claim_kind, transition)] = max(
                priorities.get((claim_kind, transition), 0),
                int(row.get("covered", 0) or 0),
            )
    return priorities


def _strategy_weight(strategy: str | None, template: Mapping[str, Any]) -> int:
    claim_kind = template["claim_kind"]
    transition = template["transition"]
    if strategy == "characterizer" and claim_kind == "necessary":
        return 80000
    if strategy == "stale" and template["key"] == "stone_persists_no_flowers":
        return 90000
    if strategy == "frontier" and transition == "W->W":
        return 50000
    if strategy == "frontier" and transition == "F->.":
        return 45000
    if strategy == "lawwright" and template["key"] == "stone_persists":
        return 80000
    if strategy == "clean" and template["key"] == "flower_wither_from_two_stones":
        return 80000
    return 0


def choose_packet_move(packet: Mapping[str, Any]) -> dict[str, Any]:
    """Choose one deterministic JSON move from a player packet."""

    player = _required_player(packet)
    player_token = _safe_conjecture_token(player)
    priorities = _candidate_priorities(packet)
    strategy = packet.get("strategy") if isinstance(packet.get("strategy"), str) else None
    ranked = []
    for index, template in enumerate(SAFE_CONJECTURE_LIBRARY):
        priority = priorities.get((template["claim_kind"], template["transition"]), -1)
        if priority < 0:
            continue
        ranked.append((_strategy_weight(strategy, template) + priority, -index, template))

    if not ranked:
        return {"type": "score", "player": player}

    _rank, _index, template = sorted(ranked, key=lambda item: (-item[0], item[1]))[0]
    return {
        "type": "conjecture",
        "player": player,
        "name": f"{player_token}_{template['key']}",
        "claim_kind": template["claim_kind"],
        "if": template["if"],
        "then": template["then"],
    }


def write_move(path: str | Path, move: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(move), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit one deterministic move from a Conjecture Golf player packet.")
    parser.add_argument("packet", help="player_packets/<player>.json")
    parser.add_argument("--out", help="Optional move JSON output path")
    args = parser.parse_args(argv)

    move = choose_packet_move(load_packet(args.packet))
    if args.out:
        write_move(args.out, move)
    print(json.dumps(move, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
