"""Closed-match rehearsal driven only by machine player packets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .closed_match import run_closed_match, write_closed_match_outputs
from .closed_test_audit import audit_records, render_audit_markdown
from .match_pack import build_match_pack
from .packet_agent import choose_packet_move, load_packet, write_move
from .replay import iter_jsonl
from .season_catalog import load_optional_compiled_season
from .season_eval import evaluate_records, render_evaluation_markdown


DEFAULT_PACKET_PARTICIPANTS = [
    "packet-frontier=frontier",
    "packet-characterizer=characterizer",
    "packet-lawwright=lawwright",
]


def _write_json(path: str | Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: str | Path, records: list[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            f.write("\n")


def _safe_player_filename(player: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in player).strip("._-")
    return (cleaned or "player")[:80]


def _participant_name(spec: str) -> str:
    raw = spec.strip()
    if "=" in raw:
        raw = raw.split("=", 1)[0]
    if ":" in raw:
        raw = raw.split(":", 1)[0]
    return raw.strip()


def run_packet_playtest(
    *,
    out_dir: str | Path,
    source: str | Path | None = None,
    participants: list[str] | None = None,
    rounds: int = 1,
    season_path: str | Path | None = None,
    reveal_policy: str = "redacted",
) -> dict[str, Any]:
    if rounds < 1:
        raise ValueError("rounds must be at least 1")
    participant_specs = participants or list(DEFAULT_PACKET_PARTICIPANTS)
    records = list(iter_jsonl(source)) if source else []
    season = load_optional_compiled_season(season_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    quarantine_records: list[dict[str, Any]] = []
    round_summaries: list[dict[str, Any]] = []

    for index in range(rounds):
        round_no = index + 1
        round_dir = out / f"round-{round_no:02d}"
        start_path = round_dir / "start.jsonl"
        pack_dir = round_dir / "match_pack"
        moves_dir = round_dir / "moves"
        _write_jsonl(start_path, records)
        build_match_pack(
            start_path,
            pack_dir,
            season_path=season_path,
            season_scoring=True,
            reveal_policy=reveal_policy,
            participants=participant_specs,
        )
        moves_dir.mkdir(parents=True, exist_ok=True)
        generated_moves: dict[str, str] = {}
        for spec in participant_specs:
            player = _participant_name(spec)
            packet_path = pack_dir / "player_packets" / f"{_safe_player_filename(player)}.json"
            move = choose_packet_move(load_packet(packet_path))
            move_path = moves_dir / f"{_safe_player_filename(player)}.json"
            write_move(move_path, move)
            generated_moves[player] = str(move_path)

        result = run_closed_match(
            start_path,
            moves_dir,
            prior_quarantine_records=quarantine_records,
            season_scoring=True,
            season=season,
        )
        outputs = write_closed_match_outputs(
            result,
            round_dir,
            season_scoring=True,
            season=season,
            reveal_policy=reveal_policy,
        )
        records = result.canonical_records
        quarantine_records = result.quarantine_records
        round_summaries.append(
            {
                "round": round_no,
                "accepted": result.accepted_count,
                "rejected": result.rejected_count,
                "generated_moves": generated_moves,
                "outputs": outputs,
            }
        )

    final_transcript = out / "final_transcript.jsonl"
    _write_jsonl(final_transcript, records)
    final_audit = audit_records(
        records,
        season=season,
        min_players=min(3, len(participant_specs)),
        min_game_moves=min(3, max(1, len(participant_specs) * rounds)),
    )
    final_eval = evaluate_records(records, season_scoring=True, season=season)
    _write_json(out / "closed_test_audit.json", final_audit.to_dict())
    (out / "closed_test_audit.md").write_text(render_audit_markdown(final_audit), encoding="utf-8")
    _write_json(out / "season_eval.json", final_eval.to_dict())
    (out / "season_eval.md").write_text(render_evaluation_markdown(final_eval), encoding="utf-8")
    next_pack = out / "next_match_pack"
    build_match_pack(
        final_transcript,
        next_pack,
        season_path=season_path,
        season_scoring=True,
        reveal_policy=reveal_policy,
        participants=participant_specs,
    )
    summary = {
        "participants": participant_specs,
        "rounds": round_summaries,
        "final_transcript": str(final_transcript),
        "next_match_pack": str(next_pack),
        "closed_test_audit": final_audit.to_dict(),
        "evaluation": final_eval.to_dict(),
        "note": (
            "This is a deterministic packet-driven rehearsal. It proves the machine packet loop works, "
            "but it is not evidence that external AI models found the game interesting."
        ),
    }
    _write_json(out / "packet_playtest_summary.json", summary)
    return summary


def run_packet_stale_drill(
    *,
    out_dir: str | Path,
    source: str | Path,
    season_path: str | Path | None = None,
    reveal_policy: str = "redacted",
) -> dict[str, Any]:
    """Run a short packet loop that proves stale scoring becomes visible."""

    season = load_optional_compiled_season(season_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    records = list(iter_jsonl(source))
    quarantine_records: list[dict[str, Any]] = []
    phases = [
        ("cover", ["packet-lawwright=lawwright"]),
        ("stale", ["packet-stale=stale"]),
    ]
    phase_summaries = []

    for phase_index, (phase_name, participants) in enumerate(phases, start=1):
        phase_dir = out / f"{phase_index:02d}-{phase_name}"
        start_path = phase_dir / "start.jsonl"
        pack_dir = phase_dir / "match_pack"
        moves_dir = phase_dir / "moves"
        _write_jsonl(start_path, records)
        build_match_pack(
            start_path,
            pack_dir,
            season_path=season_path,
            season_scoring=True,
            reveal_policy=reveal_policy,
            participants=participants,
        )
        moves_dir.mkdir(parents=True, exist_ok=True)
        generated_moves: dict[str, str] = {}
        for spec in participants:
            player = _participant_name(spec)
            packet_path = pack_dir / "player_packets" / f"{_safe_player_filename(player)}.json"
            move = choose_packet_move(load_packet(packet_path))
            move_path = moves_dir / f"{_safe_player_filename(player)}.json"
            write_move(move_path, move)
            generated_moves[player] = str(move_path)

        result = run_closed_match(
            start_path,
            moves_dir,
            prior_quarantine_records=quarantine_records,
            season_scoring=True,
            season=season,
        )
        outputs = write_closed_match_outputs(
            result,
            phase_dir,
            season_scoring=True,
            season=season,
            reveal_policy=reveal_policy,
        )
        records = result.canonical_records
        quarantine_records = result.quarantine_records
        phase_summaries.append(
            {
                "phase": phase_name,
                "accepted": result.accepted_count,
                "rejected": result.rejected_count,
                "generated_moves": generated_moves,
                "outputs": outputs,
            }
        )

    final_transcript = out / "final_transcript.jsonl"
    _write_jsonl(final_transcript, records)
    evaluation = evaluate_records(records, season_scoring=True, season=season)
    audit = audit_records(
        records,
        season=season,
        min_players=3,
        min_game_moves=3,
    )
    _write_json(out / "season_eval.json", evaluation.to_dict())
    (out / "season_eval.md").write_text(render_evaluation_markdown(evaluation), encoding="utf-8")
    _write_json(out / "closed_test_audit.json", audit.to_dict())
    (out / "closed_test_audit.md").write_text(render_audit_markdown(audit), encoding="utf-8")
    summary = {
        "phases": phase_summaries,
        "final_transcript": str(final_transcript),
        "evaluation": evaluation.to_dict(),
        "closed_test_audit": audit.to_dict(),
        "stale_pressure_visible": evaluation.stale_moves > 0,
        "note": "This drill proves stale true conjectures can remain canonical while scoring as stale.",
    }
    _write_json(out / "packet_stale_drill_summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a packet-driven closed-match rehearsal.")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--source", help="Optional seed transcript JSONL")
    parser.add_argument("--participant", action="append", dest="participants", help="player=strategy. May repeat.")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--season", help="Optional data-only season spec path")
    parser.add_argument("--reveal-policy", choices=["full", "redacted"], default="redacted")
    parser.add_argument("--stale-drill", action="store_true", help="Run the short stale-scoring packet drill.")
    args = parser.parse_args(argv)

    if args.stale_drill:
        if not args.source:
            parser.error("--stale-drill requires --source")
        summary = run_packet_stale_drill(
            out_dir=args.out,
            source=args.source,
            season_path=args.season,
            reveal_policy=args.reveal_policy,
        )
    else:
        summary = run_packet_playtest(
            out_dir=args.out,
            source=args.source,
            participants=args.participants,
            rounds=args.rounds,
            season_path=args.season,
            reveal_policy=args.reveal_policy,
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
