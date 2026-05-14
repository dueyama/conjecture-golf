"""Strict self-reported AI player profiles.

Agent profiles are transcript metadata. They help observers compare play styles,
but they are not trusted evidence and never affect scoring.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .world import ValidationError

ALLOWED_AGENT_KINDS = {"llm_agent", "scripted_agent", "human_assisted_ai", "human", "other"}
ALLOWED_AUTONOMY = {"human_paste", "human_approved", "tool_assisted", "fully_autonomous", "scripted", "unknown"}
ALLOWED_AGENT_PROFILE_KEYS = {
    "kind",
    "model_family",
    "model_name",
    "interface",
    "autonomy",
    "can_read_repo",
    "can_run_tests",
    "can_post_to_github",
    "notes",
}
ALLOWED_HELLO_KEYS = {"type", "player", "agent_profile"}
STRING_LIMITS = {
    "model_family": 80,
    "model_name": 120,
    "interface": 120,
    "notes": 500,
}


def _short_string(value: Any, label: str, *, max_len: int, required: bool = False) -> str | None:
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be a string")
    cleaned = value.strip()
    if required and not cleaned:
        raise ValidationError(f"{label} must not be empty")
    if not cleaned:
        return None
    if len(cleaned) > max_len:
        raise ValidationError(f"{label} must be no longer than {max_len} chars")
    if any(ord(ch) < 32 for ch in cleaned):
        raise ValidationError(f"{label} must not contain control characters")
    return cleaned


def _player_name(value: Any) -> str:
    player = _short_string(value, "player", max_len=80, required=True)
    assert player is not None
    return player


def validate_agent_profile(profile: Any) -> dict[str, Any]:
    """Validate an agent profile as safe, bounded JSON data."""

    if not isinstance(profile, Mapping):
        raise ValidationError("agent_profile must be an object")
    profile = dict(profile)
    unknown = set(profile) - ALLOWED_AGENT_PROFILE_KEYS
    if unknown:
        raise ValidationError(f"unknown agent_profile fields: {sorted(unknown)}")
    if "kind" not in profile:
        raise ValidationError("agent_profile requires kind")

    kind = profile["kind"]
    if not isinstance(kind, str) or kind not in ALLOWED_AGENT_KINDS:
        raise ValidationError(f"agent_profile.kind must be one of {sorted(ALLOWED_AGENT_KINDS)}")

    normalized: dict[str, Any] = {"kind": kind}
    if "autonomy" in profile:
        autonomy = profile["autonomy"]
        if not isinstance(autonomy, str) or autonomy not in ALLOWED_AUTONOMY:
            raise ValidationError(f"agent_profile.autonomy must be one of {sorted(ALLOWED_AUTONOMY)}")
        normalized["autonomy"] = autonomy

    for key, limit in STRING_LIMITS.items():
        if key in profile:
            value = _short_string(profile[key], f"agent_profile.{key}", max_len=limit)
            if value is not None:
                normalized[key] = value

    for key in ("can_read_repo", "can_run_tests", "can_post_to_github"):
        if key in profile:
            value = profile[key]
            if not isinstance(value, bool):
                raise ValidationError(f"agent_profile.{key} must be a boolean")
            normalized[key] = value

    return normalized


def validate_hello_command(command: Any) -> dict[str, Any]:
    """Validate a hello command that announces a self-reported player profile."""

    if not isinstance(command, Mapping):
        raise ValidationError("hello command must be an object")
    command = dict(command)
    unknown = set(command) - ALLOWED_HELLO_KEYS
    if unknown:
        raise ValidationError(f"unknown hello fields: {sorted(unknown)}")
    if command.get("type") != "hello":
        raise ValidationError("hello command type must be hello")
    if "player" not in command:
        raise ValidationError("hello command requires player")
    if "agent_profile" not in command:
        raise ValidationError("hello command requires agent_profile")
    return {
        "type": "hello",
        "player": _player_name(command["player"]),
        "agent_profile": validate_agent_profile(command["agent_profile"]),
    }
