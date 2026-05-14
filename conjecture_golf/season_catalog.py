"""Helpers for bundled and user-provided season specs."""

from __future__ import annotations

from pathlib import Path

from .season import repo_root
from .season_engine import CompiledSeason, load_compiled_season


def seasons_dir() -> Path:
    return repo_root() / "seasons"


def resolve_season_path(season: str | Path | None) -> Path | None:
    if season is None:
        return None
    path = Path(season)
    if path.exists():
        return path
    candidate = seasons_dir() / str(season)
    if candidate.exists():
        return candidate
    if not str(season).endswith(".json"):
        candidate = seasons_dir() / f"{season}.json"
        if candidate.exists():
            return candidate
    return path


def load_optional_compiled_season(season: str | Path | None) -> CompiledSeason | None:
    path = resolve_season_path(season)
    if path is None:
        return None
    return load_compiled_season(path)
