"""Deterministic metrics and lint warnings for season specs."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from .season_engine import compile_season
from .season_spec import SeasonSpec, SeasonSpecIssue


@dataclass(frozen=True)
class SeasonMetrics:
    season_id: str
    schema_valid: bool
    symbol_count: int
    rule_count: int
    condition_count_total: int
    condition_count_by_kind: dict[str, int]
    local_neighborhood_count: int
    transition_counts_by_before_after: dict[str, int]
    rule_hit_counts: dict[str, int]
    stay_ratio: float
    change_ratio: float
    symbols_that_can_appear_as_after: list[str]
    symbols_that_never_appear_as_after: list[str]
    symbols_that_never_change: list[str]
    unused_symbols: list[str]
    priority_shadow_warnings: list[dict[str, str]]
    readability_score: int
    tractability_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _condition_kind(condition: dict[str, Any]) -> str:
    return next(iter(condition))


def _used_symbols(spec: SeasonSpec) -> set[str]:
    used: set[str] = {"."}
    for rule in spec.rules:
        used.add(rule.becomes)
        for condition in rule.when:
            kind = _condition_kind(condition)
            value = condition[kind]
            if kind == "target_is":
                used.add(str(value))
            else:
                used.add(str(value["symbol"]))
    return used


def compute_season_metrics(spec: SeasonSpec) -> SeasonMetrics:
    engine = compile_season(spec)
    transition_counts: Counter[str] = Counter()
    rule_hits: Counter[str] = Counter({rule.id: 0 for rule in spec.rules})
    rule_hits["__default_stay__"] = 0
    can_after: set[str] = set()
    changing_symbols: set[str] = set()

    for local in engine.tiny_local_boards(size=3):
        board = engine.center_embed_3x3(local)
        before = board[2][2]
        rule = engine.first_matching_rule(board, 2, 2)
        if rule is None:
            after = before
            rule_hits["__default_stay__"] += 1
        else:
            after = rule.becomes
            rule_hits[rule.id] += 1
        transition_counts[f"{before}->{after}"] += 1
        can_after.add(after)
        if after != before:
            changing_symbols.add(before)

    local_count = spec.limits.max_local_neighborhoods
    actual_local_count = len(spec.symbols) ** 9
    condition_counts: Counter[str] = Counter()
    total_conditions = 0
    for rule in spec.rules:
        for condition in rule.when:
            condition_counts[_condition_kind(condition)] += 1
            total_conditions += 1
    stay_count = sum(count for key, count in transition_counts.items() if key.split("->", 1)[0] == key.split("->", 1)[1])
    change_count = actual_local_count - stay_count
    zero_hit_rules = [rule.id for rule in spec.rules if rule_hits[rule.id] == 0]
    priority_warnings = [
        {
            "rule_id": rule_id,
            "message": f"Rule {rule_id!r} never hits in local-neighborhood metrics; it may be shadowed or impossible.",
        }
        for rule_id in zero_hit_rules
    ]
    readability = (
        100
        - 5 * max(0, len(spec.symbols) - 4)
        - 3 * max(0, len(spec.rules) - 3)
        - total_conditions
        - 5 * len(priority_warnings)
    )
    return SeasonMetrics(
        season_id=spec.season_id,
        schema_valid=True,
        symbol_count=len(spec.symbols),
        rule_count=len(spec.rules),
        condition_count_total=total_conditions,
        condition_count_by_kind=dict(sorted(condition_counts.items())),
        local_neighborhood_count=actual_local_count,
        transition_counts_by_before_after=dict(sorted(transition_counts.items())),
        rule_hit_counts=dict(sorted(rule_hits.items())),
        stay_ratio=round(stay_count / actual_local_count, 6) if actual_local_count else 0.0,
        change_ratio=round(change_count / actual_local_count, 6) if actual_local_count else 0.0,
        symbols_that_can_appear_as_after=sorted(can_after),
        symbols_that_never_appear_as_after=sorted(spec.symbol_set - can_after),
        symbols_that_never_change=sorted(spec.symbol_set - changing_symbols),
        unused_symbols=sorted(spec.symbol_set - _used_symbols(spec)),
        priority_shadow_warnings=priority_warnings,
        readability_score=max(0, readability),
        tractability_status="ok" if actual_local_count <= local_count else "too_many_local_neighborhoods",
    )


def _issue(code: str, message: str, path: str) -> SeasonSpecIssue:
    return SeasonSpecIssue(code=code, message=message, path=path)


def lint_metrics(metrics: SeasonMetrics) -> list[SeasonSpecIssue]:
    warnings: list[SeasonSpecIssue] = []
    if metrics.change_ratio == 0:
        warnings.append(_issue("TRIVIAL_ALL_STAY", "No local neighborhoods change. This season may be trivial.", "transition"))
    elif metrics.change_ratio < 0.005:
        warnings.append(_issue("LOW_CHANGE_RATIO", "Very few local neighborhoods change. This season may be too static.", "transition"))
    elif metrics.change_ratio > 0.8:
        warnings.append(_issue("HIGH_CHANGE_RATIO", "Most local neighborhoods change. This season may be too chaotic.", "transition"))
    for symbol in metrics.unused_symbols:
        warnings.append(_issue("UNUSED_SYMBOL", f"Symbol {symbol!r} is never referenced by any rule.", "symbols"))
    for symbol in metrics.symbols_that_never_appear_as_after:
        warnings.append(_issue("SYMBOL_NEVER_APPEARS", f"Symbol {symbol!r} never appears as a next symbol.", "symbols"))
    for rule_id, count in metrics.rule_hit_counts.items():
        if rule_id != "__default_stay__" and count == 0:
            warnings.append(_issue("RULE_NEVER_HITS", f"Rule {rule_id!r} never hits.", "transition.rules"))
    if metrics.priority_shadow_warnings:
        warnings.append(
            _issue(
                "POSSIBLE_PRIORITY_SHADOWING",
                "At least one rule never hits and may be shadowed by an earlier priority.",
                "transition.rules",
            )
        )
    if metrics.readability_score < 50:
        warnings.append(_issue("VERY_LOW_READABILITY", "Readability score is below 50.", "transition"))
    return warnings


def render_metrics_markdown(metrics: SeasonMetrics) -> str:
    lines = [
        f"# Season Metrics: {metrics.season_id}",
        "",
        "| metric | value |",
        "| --- | ---: |",
        f"| symbol_count | {metrics.symbol_count} |",
        f"| rule_count | {metrics.rule_count} |",
        f"| condition_count_total | {metrics.condition_count_total} |",
        f"| local_neighborhood_count | {metrics.local_neighborhood_count} |",
        f"| stay_ratio | {metrics.stay_ratio:.6f} |",
        f"| change_ratio | {metrics.change_ratio:.6f} |",
        f"| readability_score | {metrics.readability_score} |",
        "",
        "## Transition Counts",
        "",
        "| transition | count |",
        "| --- | ---: |",
    ]
    for transition, count in metrics.transition_counts_by_before_after.items():
        lines.append(f"| {transition} | {count} |")
    lines.extend(["", "## Rule Hits", "", "| rule | count |", "| --- | ---: |"])
    for rule_id, count in metrics.rule_hit_counts.items():
        lines.append(f"| {rule_id} | {count} |")
    lines.append("")
    return "\n".join(lines)


def render_season_markdown(spec: SeasonSpec, metrics: SeasonMetrics, warnings: list[SeasonSpecIssue]) -> str:
    lines = [
        f"# Season: {spec.title}",
        "",
        f"Season id: `{spec.season_id}`",
        "",
        spec.summary,
        "",
        "## Symbols",
        "",
        "| id | name | description |",
        "| --- | --- | --- |",
    ]
    for symbol in spec.symbols:
        lines.append(f"| `{symbol.id}` | {symbol.name} | {symbol.description} |")
    lines.extend(["", "## Relations", ""])
    lines.extend(f"- `{relation}`" for relation in spec.relations)
    lines.extend(["", "## Priority Rules", ""])
    for rule in spec.rules:
        lines.append(f"- `{rule.priority}` `{rule.id}` -> `{rule.becomes}` when `{len(rule.when)}` conditions match")
    lines.extend(
        [
            "",
            "## Default Behavior",
            "",
            "`stay` when no priority rule matches.",
            "",
            "## Limits",
            "",
            f"- max symbols: `{spec.limits.max_symbols}`",
            f"- max rules: `{spec.limits.max_rules}`",
            f"- max conditions per rule: `{spec.limits.max_conditions_per_rule}`",
            f"- max local neighborhoods: `{spec.limits.max_local_neighborhoods}`",
            "",
            "## Metrics Summary",
            "",
            f"- local neighborhoods: `{metrics.local_neighborhood_count}`",
            f"- change ratio: `{metrics.change_ratio:.6f}`",
            f"- readability score: `{metrics.readability_score}`",
            "",
            "## Warnings",
            "",
        ]
    )
    if warnings:
        lines.extend(f"- `{warning.code}`: {warning.message}" for warning in warnings)
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)
