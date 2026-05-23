"""Audit a completed raw external-AI round.

The audit is the bridge between "we collected chat replies" and "this was a
usable external-AI game round." It checks preserved raw responses, strict
one-JSON intake, accepted moves, participant roster evidence, and next-pack
continuation.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ai_appeal import assess_match_pack_ai_appeal


@dataclass(frozen=True)
class ExternalRoundAuditCheck:
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
class ExternalRoundAuditReport:
    round_dir: str
    passed: bool
    score: str
    metrics: dict[str, Any]
    checks: list[ExternalRoundAuditCheck]
    next_steps: list[str]
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_dir": self.round_dir,
            "passed": self.passed,
            "score": self.score,
            "metrics": self.metrics,
            "checks": [check.to_dict() for check in self.checks],
            "next_steps": self.next_steps,
            "note": self.note,
        }


def _check(key: str, condition: bool, *, category: str, evidence: str) -> ExternalRoundAuditCheck:
    return ExternalRoundAuditCheck(key=key, passed=bool(condition), category=category, evidence=evidence)


def _load_json(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, f"missing: {path}"
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON in {path}: {exc.msg}"


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _path_exists(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and Path(value).exists()


def _load_response_reports(intake: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    reports: list[dict[str, Any]] = []
    errors: list[str] = []
    for item in intake:
        report_path = item.get("report")
        if not isinstance(report_path, str) or not report_path.strip():
            errors.append(f"{item.get('expected_player')}: missing report path")
            continue
        payload, error = _load_json(Path(report_path))
        if error:
            errors.append(error)
            continue
        if not isinstance(payload, dict):
            errors.append(f"{report_path}: report must be an object")
            continue
        reports.append(dict(payload, report_path=report_path))
    return reports, errors


def _load_roster(path: Any) -> tuple[list[dict[str, Any]], str | None]:
    if not isinstance(path, str) or not path.strip():
        return [], "missing participant roster path"
    payload, error = _load_json(Path(path))
    if error:
        return [], error
    if not isinstance(payload, dict) or not isinstance(payload.get("participants"), list):
        return [], "participant roster must be an object with participants list"
    entries: list[dict[str, Any]] = []
    for index, item in enumerate(payload["participants"], start=1):
        if not isinstance(item, dict):
            return [], f"participant {index} must be an object"
        player = str(item.get("player", "")).strip()
        if not player:
            return [], f"participant {index} missing player"
        entries.append(dict(item, player=player))
    return entries, None


def _model_identity(entry: dict[str, Any]) -> str:
    return str(entry.get("model") or entry.get("model_name") or entry.get("model_family") or "").strip()


def _safe_reports_by_player(reports: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    safe: dict[str, dict[str, Any]] = {}
    for report in reports:
        player = str(report.get("expected_player") or report.get("player") or "").strip()
        if not player:
            continue
        if (
            report.get("contract_ok") is True
            and report.get("status") == "strict_json"
            and report.get("player_matches_expected") is not False
            and int(report.get("json_objects_found", 0) or 0) == 1
        ):
            safe[player] = report
    return safe


def audit_external_round(
    round_dir: str | Path,
    *,
    min_external_participants: int = 2,
    min_distinct_models: int = 1,
    require_model_info: bool = False,
    require_next_pack_appeal: bool = False,
    validate_next_pack_packets: bool = False,
) -> ExternalRoundAuditReport:
    root = Path(round_dir)
    checks: list[ExternalRoundAuditCheck] = []
    metrics: dict[str, Any] = {}
    next_steps: list[str] = []

    root_exists = root.exists() and root.is_dir()
    checks.append(
        _check(
            "round_directory_exists",
            root_exists,
            category="structure",
            evidence=f"round directory: {root}",
        )
    )
    if not root_exists:
        return ExternalRoundAuditReport(
            round_dir=str(root),
            passed=False,
            score="0/1",
            metrics=metrics,
            checks=checks,
            next_steps=["Run season0 raw-round before auditing an external round."],
            note="This audit checks local evidence only; it cannot prove which remote model typed a response.",
        )

    summary, summary_error = _load_json(root / "external_round_summary.json")
    summary_map = _mapping(summary)
    checks.append(
        _check(
            "external_round_summary_exists",
            summary_error is None and bool(summary_map),
            category="structure",
            evidence=summary_error or "external_round_summary.json parsed.",
        )
    )

    intake = [dict(item) for item in _list(summary_map.get("response_intake")) if isinstance(item, dict)]
    raw_responses = int(summary_map.get("raw_responses", 0) or 0)
    moves_written = int(summary_map.get("moves_written", 0) or 0)
    accepted = int(summary_map.get("accepted", 0) or 0)
    rejected = int(summary_map.get("rejected", 0) or 0)
    allow_extraction = bool(summary_map.get("allow_extraction", False))
    expected_players = sorted(str(item.get("expected_player", "")).strip() for item in intake if item.get("expected_player"))
    metrics.update(
        {
            "raw_responses": raw_responses,
            "moves_written": moves_written,
            "accepted": accepted,
            "rejected": rejected,
            "allow_extraction": allow_extraction,
            "expected_players": expected_players,
        }
    )
    checks.append(
        _check(
            "enough_external_responses",
            raw_responses >= min_external_participants and len(expected_players) >= min_external_participants,
            category="participants",
            evidence=f"{raw_responses} raw responses, players={expected_players}.",
        )
    )

    missing_paths: list[str] = []
    for item in intake:
        for key in ("raw_copy", "report"):
            if not _path_exists(item.get(key)):
                missing_paths.append(f"{item.get('expected_player')}:{key}")
        if item.get("wrote_move") is True and not _path_exists(item.get("move")):
            missing_paths.append(f"{item.get('expected_player')}:move")
    checks.append(
        _check(
            "raw_reports_and_moves_are_preserved",
            not missing_paths and bool(intake),
            category="provenance",
            evidence="raw copies, reports, and written moves exist"
            if not missing_paths and intake
            else "; ".join(missing_paths[:8]) or "no response intake rows",
        )
    )

    reports, report_errors = _load_response_reports(intake)
    safe_reports = _safe_reports_by_player(reports)
    contract_failures = [
        str(item.get("expected_player"))
        for item in intake
        if item.get("contract_ok") is not True
        or item.get("status") != "strict_json"
        or item.get("violations")
        or item.get("allow_extraction")
        or item.get("duplicate_player_response")
        or item.get("wrote_move") is not True
    ]
    checks.append(
        _check(
            "strict_json_contract_passed_for_all_responses",
            not allow_extraction and not report_errors and not contract_failures and len(safe_reports) == len(intake),
            category="provenance",
            evidence="all raw responses were strict one-object JSON and wrote one move"
            if not allow_extraction and not report_errors and not contract_failures and len(safe_reports) == len(intake)
            else "; ".join(report_errors[:4] + contract_failures[:6]) or "safe report count mismatch",
        )
    )

    checks.append(
        _check(
            "all_written_moves_entered_canonical_round",
            raw_responses == moves_written == accepted and rejected == 0 and accepted > 0,
            category="judging",
            evidence=f"raw={raw_responses}, written={moves_written}, accepted={accepted}, rejected={rejected}.",
        )
    )

    roster_entries, roster_error = _load_roster(summary_map.get("participant_roster_template"))
    roster_players = sorted(entry["player"] for entry in roster_entries)
    external_entries = [entry for entry in roster_entries if entry.get("external") is True]
    model_identities = sorted({_model_identity(entry) for entry in external_entries if _model_identity(entry)})
    missing_model_info = sorted(entry["player"] for entry in external_entries if not _model_identity(entry))
    metrics.update(
        {
            "roster_players": roster_players,
            "external_participants": len(external_entries),
            "distinct_models": len(model_identities),
            "missing_model_info": missing_model_info,
        }
    )
    checks.append(
        _check(
            "participant_roster_matches_intake",
            roster_error is None and roster_players == expected_players,
            category="participants",
            evidence=f"roster={roster_players}, intake={expected_players}."
            if roster_error is None
            else roster_error,
        )
    )
    model_info_ok = len(model_identities) >= min_distinct_models and (not require_model_info or not missing_model_info)
    checks.append(
        _check(
            "external_roster_has_model_evidence",
            len(external_entries) >= min_external_participants and model_info_ok,
            category="participants",
            evidence=(
                f"{len(external_entries)} external entries, {len(model_identities)} distinct model identities, "
                f"missing model info={missing_model_info or 'none'}."
            ),
        )
    )
    if require_model_info and missing_model_info:
        next_steps.append("Fill model/model_name/model_family for every external roster entry before final evidence.")

    closed_test_audit = _mapping(summary_map.get("closed_test_audit"))
    checks.append(
        _check(
            "closed_test_audit_written",
            bool(closed_test_audit.get("checks")) or "passed" in closed_test_audit,
            category="judging",
            evidence=f"closed_test_audit.passed={closed_test_audit.get('passed')}.",
        )
    )

    next_pack_path = summary_map.get("next_match_pack")
    next_pack_exists = isinstance(next_pack_path, str) and Path(next_pack_path).exists()
    checks.append(
        _check(
            "next_match_pack_exists",
            next_pack_exists,
            category="continuity",
            evidence=f"next match pack: {next_pack_path}",
        )
    )
    if next_pack_exists:
        next_appeal = assess_match_pack_ai_appeal(
            Path(str(next_pack_path)),
            validate_packets=validate_next_pack_packets,
            min_participants=min_external_participants,
        )
        metrics["next_pack_ai_appeal"] = next_appeal.to_dict()
        next_pack_ok = next_appeal.passed or not require_next_pack_appeal
        checks.append(
            _check(
                "next_pack_ai_appeal_checked",
                next_pack_ok,
                category="continuity",
                evidence=f"next pack AI appeal score {next_appeal.score}, passed={next_appeal.passed}.",
            )
        )
        if require_next_pack_appeal and not next_appeal.passed:
            next_steps.append("Regenerate or continue the next match pack until ai-appeal passes.")
    else:
        checks.append(
            _check(
                "next_pack_ai_appeal_checked",
                not require_next_pack_appeal,
                category="continuity",
                evidence="next match pack missing; cannot check AI appeal.",
            )
        )
        next_steps.append("Generate a next match pack so the same participants can continue.")

    if not next_steps:
        next_steps.append("Run another external round, then bundle final evidence after enough moves accumulate.")

    passed_checks = sum(1 for check in checks if check.passed)
    passed = passed_checks == len(checks)
    return ExternalRoundAuditReport(
        round_dir=str(root),
        passed=passed,
        score=f"{passed_checks}/{len(checks)}",
        metrics=metrics,
        checks=checks,
        next_steps=next_steps,
        note=(
            "This audit proves deterministic local handling of preserved external-AI replies. "
            "It does not cryptographically prove the remote model identity; the roster remains "
            "operator-supplied evidence."
        ),
    )


def render_external_round_audit_markdown(report: ExternalRoundAuditReport) -> str:
    lines = [
        "# External Round Audit",
        "",
        f"Passed: `{str(report.passed).lower()}`",
        f"Score: `{report.score}`",
        f"Round directory: `{report.round_dir}`",
        "",
        report.note,
        "",
        "## Metrics",
        "",
        "| metric | value |",
        "| --- | --- |",
    ]
    for key, value in sorted(report.metrics.items()):
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
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
    lines.extend(["", "## Next Steps", ""])
    for step in report.next_steps:
        lines.append(f"- {step}")
    lines.append("")
    return "\n".join(lines)


def write_external_round_audit(
    round_dir: str | Path,
    report: ExternalRoundAuditReport,
    *,
    json_name: str = "external_round_audit.json",
    markdown_name: str = "external_round_audit.md",
) -> None:
    root = Path(round_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / json_name).write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (root / markdown_name).write_text(render_external_round_audit_markdown(report), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit a completed raw external-AI round.")
    parser.add_argument("round_dir", help="Directory written by season0 raw-round")
    parser.add_argument("--min-external-participants", type=int, default=2)
    parser.add_argument("--min-distinct-models", type=int, default=1)
    parser.add_argument(
        "--require-model-info",
        action="store_true",
        help="Require every external roster entry to include model/model_name/model_family.",
    )
    parser.add_argument(
        "--require-next-pack-appeal",
        action="store_true",
        help="Fail unless the generated next_match_pack passes ai-appeal.",
    )
    parser.add_argument(
        "--validate-next-pack-packets",
        action="store_true",
        help="Run packet validation while checking next_match_pack ai-appeal.",
    )
    parser.add_argument("--write", action="store_true", help="Write external_round_audit.json/md into the round dir.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    args = parser.parse_args(argv)

    report = audit_external_round(
        args.round_dir,
        min_external_participants=args.min_external_participants,
        min_distinct_models=args.min_distinct_models,
        require_model_info=args.require_model_info,
        require_next_pack_appeal=args.require_next_pack_appeal,
        validate_next_pack_packets=args.validate_next_pack_packets,
    )
    if args.write:
        write_external_round_audit(args.round_dir, report)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_external_round_audit_markdown(report))
    return 0 if report.passed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
