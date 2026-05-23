"""Built-in local agents for deterministic Conjecture Golf demos.

These agents are intentionally simple and do not call external AI APIs. They
exist to exercise the game loop and generate readable public transcripts.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from typing import Any

from .replay import ReplayState
from .verify import check_counterexample, verify_conjecture

Command = dict[str, Any]

SYMBOLS = [".", "F", "W", "S"]
RELATIONS = ["orthogonal", "diagonal", "king"]
ORIGINAL_COUNTEREXAMPLE_BOARDS = [
    [".W...", ".....", ".SF..", ".....", "....."],
    [".....", ".W...", "..F..", ".S...", "....."],
]


def available_agents() -> tuple[str, ...]:
    return (
        "rule",
        "frontier",
        "characterizer",
        "greedy",
        "counterexample",
        "original_refuter",
        "minimalist",
        "random",
        "noise",
        "copycat",
        "narrow_spam",
    )


def _known_against(commands: Sequence[Mapping[str, Any]]) -> set[str]:
    return {
        command["against"]
        for command in commands
        if command.get("type") == "counterexample" and isinstance(command.get("against"), str)
    }


def rule_agent_command(player: str, turn_index: int) -> Command:
    commands: list[Command] = [
        {
            "type": "conjecture",
            "player": player,
            "name": "rule_flower_growth",
            "if": [
                {"target_is": "."},
                {"exists": {"symbol": "W", "relation": "diagonal"}},
                {"exists": {"symbol": "F", "relation": "orthogonal"}},
                {"not_exists": {"symbol": "S", "relation": "king"}},
            ],
            "then": {"target_becomes": "F"},
        },
        {
            "type": "conjecture",
            "player": player,
            "name": "rule_flower_wither",
            "if": [
                {"target_is": "F"},
                {"count_at_least": {"symbol": "S", "relation": "king", "n": 2}},
            ],
            "then": {"target_becomes": "."},
        },
        {
            "type": "conjecture",
            "player": player,
            "name": "rule_water_spread",
            "if": [
                {"target_is": "."},
                {"count_exactly": {"symbol": "W", "relation": "orthogonal", "n": 2}},
                {"not_exists": {"symbol": "S", "relation": "diagonal"}},
                {"not_exists": {"symbol": "W", "relation": "diagonal"}},
            ],
            "then": {"target_becomes": "W"},
        },
        {
            "type": "conjecture",
            "player": player,
            "name": "rule_trapped_water_evaporates",
            "if": [
                {"target_is": "W"},
                {"not_exists": {"symbol": ".", "relation": "orthogonal"}},
            ],
            "then": {"target_becomes": "."},
        },
    ]
    if turn_index < len(commands):
        return commands[turn_index]
    return {"type": "score", "player": player}


def greedy_agent_command(player: str, turn_index: int) -> Command:
    commands: list[Command] = [
        {
            "type": "conjecture",
            "player": player,
            "name": "greedy_flower_growth_too_broad",
            "if": [
                {"target_is": "."},
                {"exists": {"symbol": "W", "relation": "diagonal"}},
                {"exists": {"symbol": "F", "relation": "orthogonal"}},
            ],
            "then": {"target_becomes": "F"},
        },
        {
            "type": "conjecture",
            "player": player,
            "name": "greedy_any_water_evaporates",
            "if": [{"target_is": "W"}],
            "then": {"target_becomes": "."},
        },
        {
            "type": "conjecture",
            "player": player,
            "name": "greedy_any_flower_survives",
            "if": [{"target_is": "F"}],
            "then": {"target_becomes": "F"},
        },
    ]
    if turn_index < len(commands):
        return commands[turn_index]
    return {"type": "score", "player": player}


def characterizer_agent_command(player: str, turn_index: int) -> Command:
    commands: list[Command] = [
        {
            "type": "conjecture",
            "player": player,
            "name": "characterize_stone_persistence",
            "claim_kind": "equivalence",
            "if": [{"target_is": "S"}],
            "then": {"target_becomes": "S"},
        },
        {
            "type": "conjecture",
            "player": player,
            "name": "stone_output_requires_stone_input",
            "claim_kind": "necessary",
            "if": [{"target_is": "S"}],
            "then": {"target_becomes": "S"},
        },
    ]
    if turn_index < len(commands):
        return commands[turn_index]
    return {"type": "score", "player": player}


def frontier_agent_command(player: str, turn_index: int) -> Command:
    commands: list[Command] = [
        {
            "type": "conjecture",
            "player": player,
            "name": "frontier_water_survives_with_empty_neighbor",
            "if": [
                {"target_is": "W"},
                {"exists": {"symbol": ".", "relation": "orthogonal"}},
            ],
            "then": {"target_becomes": "W"},
        },
        {
            "type": "conjecture",
            "player": player,
            "name": "frontier_flower_survives_without_stone",
            "if": [
                {"target_is": "F"},
                {"not_exists": {"symbol": "S", "relation": "king"}},
            ],
            "then": {"target_becomes": "F"},
        },
        {
            "type": "conjecture",
            "player": player,
            "name": "frontier_water_spread_no_diagonal_water_or_stone",
            "if": [
                {"target_is": "."},
                {"count_exactly": {"symbol": "W", "relation": "orthogonal", "n": 2}},
                {"not_exists": {"symbol": "S", "relation": "diagonal"}},
                {"not_exists": {"symbol": "W", "relation": "diagonal"}},
            ],
            "then": {"target_becomes": "W"},
        },
    ]
    if turn_index < len(commands):
        return commands[turn_index]
    return {"type": "score", "player": player}


def counterexample_agent_command(
    player: str,
    state: ReplayState,
    prior_commands: Sequence[Mapping[str, Any]],
) -> Command:
    already_countered = _known_against(prior_commands)
    for name, before in state.auto_counterexamples.items():
        if name in already_countered:
            continue
        return {
            "type": "counterexample",
            "player": player,
            "against": name,
            "before": list(before),
        }
    for name, conjecture in state.conjectures.items():
        if name in already_countered:
            continue
        verdict = verify_conjecture(conjecture)
        details = verdict.details or {}
        counterexample = details.get("counterexample")
        if not verdict.ok and isinstance(counterexample, Mapping):
            before = counterexample.get("board")
            if isinstance(before, list):
                return {
                    "type": "counterexample",
                    "player": player,
                    "against": name,
                    "before": before,
                }
    return {"type": "score", "player": player}


def original_refuter_agent_command(
    player: str,
    state: ReplayState,
    prior_commands: Sequence[Mapping[str, Any]],
) -> Command:
    already_countered = _known_against(prior_commands)
    for name, conjecture in state.conjectures.items():
        if name in already_countered:
            continue
        revealed = state.auto_counterexamples.get(name)
        for before in ORIGINAL_COUNTEREXAMPLE_BOARDS:
            if tuple(before) == revealed:
                continue
            verdict = check_counterexample(dict(conjecture), before)
            if verdict.ok:
                return {
                    "type": "counterexample",
                    "player": player,
                    "against": name,
                    "before": before,
                }
    return {"type": "score", "player": player}


def minimalist_agent_command(
    player: str,
    state: ReplayState,
    prior_commands: Sequence[Mapping[str, Any]],
) -> Command:
    already_countered = _known_against(prior_commands)
    candidates: list[tuple[int, str, list[str]]] = []
    for name, before in state.auto_counterexamples.items():
        if name in already_countered:
            continue
        board = list(before)
        occupied = sum(ch != "." for row in board for ch in row)
        candidates.append((occupied, name, board))
    for name, conjecture in state.conjectures.items():
        if name in already_countered or name in state.auto_counterexamples:
            continue
        verdict = verify_conjecture(conjecture)
        details = verdict.details or {}
        counterexample = details.get("counterexample")
        if verdict.ok or not isinstance(counterexample, Mapping):
            continue
        before = counterexample.get("board")
        if isinstance(before, list) and all(isinstance(row, str) for row in before):
            occupied = sum(ch != "." for row in before for ch in row)
            candidates.append((occupied, name, list(before)))
    if not candidates:
        return {"type": "score", "player": player}

    occupied, name, before = sorted(candidates, key=lambda item: (item[0], item[1]))[0]
    return {
        "type": "counterexample",
        "player": player,
        "against": name,
        "before": before,
    }


def copycat_agent_command(player: str, prior_commands: Sequence[Mapping[str, Any]], turn_index: int) -> Command:
    for command in prior_commands:
        if command.get("type") != "conjecture":
            continue
        source = command.get("conjecture") if isinstance(command.get("conjecture"), Mapping) else command
        copied = {
            "type": "conjecture",
            "player": player,
            "name": f"copycat_{turn_index}_{source.get('name', 'claim')}",
            "if": source.get("if"),
            "then": source.get("then"),
        }
        if "claim_kind" in source:
            copied["claim_kind"] = source["claim_kind"]
        return copied
    return {"type": "score", "player": player}


def narrow_spam_agent_command(player: str, turn_index: int) -> Command:
    commands: list[Command] = [
        {
            "type": "conjecture",
            "player": player,
            "name": f"narrow_flower_growth_redundant_{turn_index}",
            "if": [
                {"target_is": "."},
                {"exists": {"symbol": "W", "relation": "diagonal"}},
                {"exists": {"symbol": "F", "relation": "orthogonal"}},
                {"not_exists": {"symbol": "S", "relation": "king"}},
                {"count_at_least": {"symbol": "W", "relation": "diagonal", "n": 1}},
            ],
            "then": {"target_becomes": "F"},
        }
    ]
    if turn_index < len(commands):
        return commands[turn_index]
    return {"type": "score", "player": player}


def random_agent_command(player: str, turn_index: int, seed: int) -> Command:
    rng = random.Random(seed + turn_index)
    target = rng.choice(SYMBOLS)
    neighbor = rng.choice(SYMBOLS)
    relation = rng.choice(RELATIONS)
    result = rng.choice(SYMBOLS)
    return {
        "type": "conjecture",
        "player": player,
        "name": f"random_{turn_index}_{target}_{neighbor}_{relation}_{result}".replace(".", "empty"),
        "if": [
            {"target_is": target},
            {"exists": {"symbol": neighbor, "relation": relation}},
        ],
        "then": {"target_becomes": result},
    }


def noise_agent_command(player: str, turn_index: int) -> Command:
    return {
        "type": "score",
        "player": player,
        "bonus": 999,
        "note": f"invalid public noise {turn_index}",
    }


def next_agent_command(
    agent_name: str,
    *,
    player: str,
    state: ReplayState,
    prior_commands: Sequence[Mapping[str, Any]],
    turn_index: int,
    seed: int,
) -> Command:
    if agent_name == "rule":
        return rule_agent_command(player, turn_index)
    if agent_name == "frontier":
        return frontier_agent_command(player, turn_index)
    if agent_name == "characterizer":
        return characterizer_agent_command(player, turn_index)
    if agent_name == "greedy":
        return greedy_agent_command(player, turn_index)
    if agent_name == "counterexample":
        return counterexample_agent_command(player, state, prior_commands)
    if agent_name == "original_refuter":
        return original_refuter_agent_command(player, state, prior_commands)
    if agent_name == "minimalist":
        return minimalist_agent_command(player, state, prior_commands)
    if agent_name == "copycat":
        return copycat_agent_command(player, prior_commands, turn_index)
    if agent_name == "narrow_spam":
        return narrow_spam_agent_command(player, turn_index)
    if agent_name == "random":
        return random_agent_command(player, turn_index, seed)
    if agent_name == "noise":
        return noise_agent_command(player, turn_index)
    raise ValueError(f"unknown local agent: {agent_name}")
