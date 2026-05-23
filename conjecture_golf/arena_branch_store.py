"""Build branch-ready arena snapshots from deterministic routing artifacts."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .arena_gate import DEFAULT_INVALID_STRIKES_TO_DISQUALIFY, iter_quarantine_jsonl
from .replay import iter_jsonl

_SAFE_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


def _safe_branch_path(out_dir: Path, branch: str) -> Path:
    if (
        not _SAFE_BRANCH_RE.fullmatch(branch)
        or branch.endswith("/")
        or "//" in branch
        or ".." in branch.split("/")
    ):
        raise ValueError(f"unsafe branch name: {branch!r}")
    return out_dir.joinpath(*branch.split("/"))


def _write_json(path: Path, payload: Mapping[str, Any] | Sequence[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(dict(record), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def _read_decisions(path: str | Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("routing decision payload must be a JSON object")
    decisions = payload.get("decisions", [])
    if not isinstance(decisions, list):
        raise ValueError("routing decision payload must contain a decisions array")
    if not all(isinstance(item, dict) for item in decisions):
        raise ValueError("routing decisions must be JSON objects")
    return [dict(item) for item in decisions]


def disqualified_players(
    quarantine_records: Sequence[Mapping[str, Any]],
    *,
    invalid_strikes_to_disqualify: int = DEFAULT_INVALID_STRIKES_TO_DISQUALIFY,
) -> list[dict[str, Any]]:
    """Return players whose invalid quarantine strikes bar canonical entry."""

    strikes: dict[str, int] = {}
    for record in quarantine_records:
        player = record.get("player")
        verdict = record.get("verdict")
        if not isinstance(player, str) or not isinstance(verdict, Mapping):
            continue
        if verdict.get("kind") != "invalid":
            continue
        strikes[player] = strikes.get(player, 0) + 1
    return [
        {
            "player": player,
            "invalid_strikes": count,
            "threshold": invalid_strikes_to_disqualify,
        }
        for player, count in sorted(strikes.items())
        if count >= invalid_strikes_to_disqualify
    ]


def write_branch_store(
    *,
    canonical_records: Sequence[Mapping[str, Any]],
    quarantine_records: Sequence[Mapping[str, Any]],
    decisions: Sequence[Mapping[str, Any]],
    out_dir: str | Path,
    canonical_branch: str = "arena/season-0",
    quarantine_branch: str = "quarantine/season-0",
    invalid_strikes_to_disqualify: int = DEFAULT_INVALID_STRIKES_TO_DISQUALIFY,
) -> dict[str, Any]:
    """Write deterministic branch snapshots and return the manifest."""

    out = Path(out_dir)
    canonical_dir = _safe_branch_path(out, canonical_branch)
    quarantine_dir = _safe_branch_path(out, quarantine_branch)
    disqualified = disqualified_players(
        quarantine_records,
        invalid_strikes_to_disqualify=invalid_strikes_to_disqualify,
    )

    canonical_state = {
        "branch": canonical_branch,
        "kind": "canonical",
        "records": len(canonical_records),
        "quarantine_branch": quarantine_branch,
        "description": "Accepted Conjecture Golf commands only. Replay this transcript locally.",
    }
    quarantine_state = {
        "branch": quarantine_branch,
        "canonical_branch": canonical_branch,
        "disqualified_players": disqualified,
        "kind": "quarantine",
        "records": len(quarantine_records),
        "strike_threshold": invalid_strikes_to_disqualify,
        "description": "Rejected commands and strike ledger. These records are not canonical game moves.",
    }

    _write_jsonl(canonical_dir / "transcript.jsonl", canonical_records)
    _write_json(canonical_dir / "branch-state.json", canonical_state)
    (canonical_dir / "README.md").write_text(
        "\n".join(
            [
                "# Conjecture Golf Canonical Arena Branch",
                "",
                f"Branch: `{canonical_branch}`",
                "",
                "This snapshot contains only accepted public game commands.",
                "Replay it with:",
                "",
                "```bash",
                "python -m conjecture_golf.replay transcript.jsonl --season-scoring",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )

    _write_jsonl(quarantine_dir / "quarantine.jsonl", quarantine_records)
    _write_json(quarantine_dir / "branch-state.json", quarantine_state)
    _write_json(quarantine_dir / "disqualified_players.json", disqualified)
    (quarantine_dir / "README.md").write_text(
        "\n".join(
            [
                "# Conjecture Golf Quarantine Branch",
                "",
                f"Branch: `{quarantine_branch}`",
                "",
                "This snapshot contains rejected public commands and the invalid-strike ledger.",
                "Players at or above the strike threshold are barred from the canonical branch for this season.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    manifest = {
        "canonical_branch": canonical_branch,
        "quarantine_branch": quarantine_branch,
        "branches": {
            canonical_branch: {
                "kind": "canonical",
                "path": str(canonical_dir.relative_to(out)),
                "records": len(canonical_records),
                "files": ["README.md", "branch-state.json", "transcript.jsonl"],
            },
            quarantine_branch: {
                "kind": "quarantine",
                "path": str(quarantine_dir.relative_to(out)),
                "records": len(quarantine_records),
                "files": ["README.md", "branch-state.json", "disqualified_players.json", "quarantine.jsonl"],
            },
        },
        "decisions": len(decisions),
        "disqualified_players": disqualified,
        "invalid_strikes_to_disqualify": invalid_strikes_to_disqualify,
    }
    _write_json(out / "branch-store-manifest.json", manifest)
    if decisions:
        _write_json(out / "routing-decisions.json", {"decisions": list(decisions)})
    return manifest


def _find_artifact(root: Path, name: str) -> Path:
    matches = sorted(path for path in root.rglob(name) if path.is_file())
    if not matches:
        raise ValueError(f"artifact {name!r} not found under {root}")
    return matches[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build branch-ready arena snapshots from routing artifacts.")
    parser.add_argument("--artifact-root", help="Directory containing arena-routing.json and transcript artifacts")
    parser.add_argument("--canonical", help="Canonical transcript JSONL path")
    parser.add_argument("--quarantine", help="Quarantine JSONL path")
    parser.add_argument("--decision", help="Routing decision JSON path")
    parser.add_argument("--out", required=True, help="Output directory for branch snapshots")
    parser.add_argument("--canonical-branch", default="arena/season-0")
    parser.add_argument("--quarantine-branch", default="quarantine/season-0")
    parser.add_argument("--invalid-strikes-to-disqualify", type=int, default=DEFAULT_INVALID_STRIKES_TO_DISQUALIFY)
    args = parser.parse_args(argv)

    artifact_root = Path(args.artifact_root) if args.artifact_root else None
    canonical_path = Path(args.canonical) if args.canonical else None
    quarantine_path = Path(args.quarantine) if args.quarantine else None
    decision_path = Path(args.decision) if args.decision else None
    if artifact_root is not None:
        canonical_path = canonical_path or _find_artifact(artifact_root, "arena-transcript.jsonl")
        quarantine_path = quarantine_path or _find_artifact(artifact_root, "quarantine-transcript.jsonl")
        decision_path = decision_path or _find_artifact(artifact_root, "arena-routing.json")
    if canonical_path is None or quarantine_path is None:
        parser.error("--canonical and --quarantine are required unless --artifact-root is provided")

    manifest = write_branch_store(
        canonical_records=list(iter_jsonl(canonical_path)) if canonical_path.exists() else [],
        quarantine_records=iter_quarantine_jsonl(quarantine_path) if quarantine_path.exists() else [],
        decisions=_read_decisions(decision_path),
        out_dir=args.out,
        canonical_branch=args.canonical_branch,
        quarantine_branch=args.quarantine_branch,
        invalid_strikes_to_disqualify=args.invalid_strikes_to_disqualify,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
