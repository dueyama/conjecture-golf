"""Season metadata helpers."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def load_season_manifest() -> dict[str, Any]:
    path = repo_root() / "season_manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def season_id() -> str:
    return str(load_season_manifest()["season_id"])
