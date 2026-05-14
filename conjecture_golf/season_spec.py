"""Data-only season specification validation and CLI."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .world import ValidationError, canonical_test_boards

SCHEMA_VERSION = "season-spec-v0.1"
ALLOWED_RELATIONS = {"orthogonal", "diagonal", "king"}
ALLOWED_CONDITION_KINDS = {"target_is", "exists", "not_exists", "count_at_least", "count_exactly"}
ALLOWED_CLAIM_KINDS = {"sufficient", "necessary", "equivalence"}
REQUIRED_TOP_LEVEL_KEYS = {
    "schema_version",
    "season_id",
    "title",
    "summary",
    "designer",
    "board",
    "symbols",
    "relations",
    "transition",
    "conjecture_dsl",
    "presentation",
    "limits",
}
ALLOWED_TOP_LEVEL_KEYS = REQUIRED_TOP_LEVEL_KEYS


@dataclass(frozen=True)
class SeasonSpecIssue:
    code: str
    message: str
    path: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class SymbolSpec:
    id: str
    name: str
    description: str


@dataclass(frozen=True)
class TransitionRule:
    id: str
    priority: int
    when: tuple[dict[str, Any], ...]
    becomes: str


@dataclass(frozen=True)
class ConjectureDslSpec:
    claim_kinds: tuple[str, ...]
    condition_kinds: tuple[str, ...]
    max_conditions: int


@dataclass(frozen=True)
class PresentationSpec:
    redaction_policy: str
    observer_title: str


@dataclass(frozen=True)
class LimitsSpec:
    max_symbols: int
    max_rules: int
    max_conditions_per_rule: int
    max_local_neighborhoods: int


@dataclass(frozen=True)
class SeasonSpec:
    schema_version: str
    season_id: str
    title: str
    summary: str
    designer: str
    width: int
    height: int
    symbols: tuple[SymbolSpec, ...]
    relations: tuple[str, ...]
    rules: tuple[TransitionRule, ...]
    conjecture_dsl: ConjectureDslSpec
    presentation: PresentationSpec
    limits: LimitsSpec
    raw: dict[str, Any]

    @property
    def symbol_ids(self) -> tuple[str, ...]:
        return tuple(symbol.id for symbol in self.symbols)

    @property
    def symbol_set(self) -> set[str]:
        return set(self.symbol_ids)


@dataclass(frozen=True)
class SeasonSpecValidationResult:
    ok: bool
    errors: tuple[SeasonSpecIssue, ...]
    warnings: tuple[SeasonSpecIssue, ...] = ()
    spec: SeasonSpec | None = None

    def to_dict(self, *, include_spec: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "errors": [issue.to_dict() for issue in self.errors],
            "warnings": [issue.to_dict() for issue in self.warnings],
        }
        if include_spec and self.spec is not None:
            payload["season_id"] = self.spec.season_id
            payload["schema_version"] = self.spec.schema_version
        return payload


def _issue(code: str, message: str, path: str) -> SeasonSpecIssue:
    return SeasonSpecIssue(code=code, message=message, path=path)


def _as_mapping(value: Any, path: str, errors: list[SeasonSpecIssue], code: str = "INVALID_FIELD") -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        errors.append(_issue(code, "must be an object", path))
        return None
    return value


def _unknown_fields(
    value: Mapping[str, Any],
    *,
    allowed: set[str],
    path: str,
    errors: list[SeasonSpecIssue],
    code: str = "UNKNOWN_FIELD",
) -> None:
    for key in sorted(set(value) - allowed):
        errors.append(_issue(code, f"unknown field: {key}", f"{path}.{key}" if path else key))


def _missing_fields(value: Mapping[str, Any], *, required: set[str], path: str, errors: list[SeasonSpecIssue]) -> None:
    for key in sorted(required - set(value)):
        errors.append(_issue("MISSING_REQUIRED_FIELD", f"missing required field: {key}", f"{path}.{key}" if path else key))


def _short_string(value: Any, path: str, errors: list[SeasonSpecIssue], *, code: str = "INVALID_FIELD") -> str:
    if not isinstance(value, str) or not value.strip():
        errors.append(_issue(code, "must be a non-empty string", path))
        return ""
    if len(value) > 200:
        errors.append(_issue(code, "must be 200 characters or shorter", path))
    return value.strip()


def _int_value(value: Any, path: str, errors: list[SeasonSpecIssue], *, code: str = "INVALID_FIELD") -> int:
    if not isinstance(value, int):
        errors.append(_issue(code, "must be an integer", path))
        return 0
    return value


def _parse_limits(data: Mapping[str, Any], errors: list[SeasonSpecIssue]) -> LimitsSpec:
    raw = _as_mapping(data.get("limits"), "limits", errors)
    defaults = LimitsSpec(max_symbols=5, max_rules=5, max_conditions_per_rule=6, max_local_neighborhoods=1_953_125)
    if raw is None:
        return defaults
    required = {"max_symbols", "max_rules", "max_conditions_per_rule", "max_local_neighborhoods"}
    _unknown_fields(raw, allowed=required, path="limits", errors=errors)
    _missing_fields(raw, required=required, path="limits", errors=errors)
    max_symbols = _int_value(raw.get("max_symbols", defaults.max_symbols), "limits.max_symbols", errors)
    max_rules = _int_value(raw.get("max_rules", defaults.max_rules), "limits.max_rules", errors)
    max_conditions = _int_value(raw.get("max_conditions_per_rule", defaults.max_conditions_per_rule), "limits.max_conditions_per_rule", errors)
    max_local = _int_value(raw.get("max_local_neighborhoods", defaults.max_local_neighborhoods), "limits.max_local_neighborhoods", errors)
    for name, value in [
        ("max_symbols", max_symbols),
        ("max_rules", max_rules),
        ("max_conditions_per_rule", max_conditions),
        ("max_local_neighborhoods", max_local),
    ]:
        if value <= 0:
            errors.append(_issue("INVALID_LIMIT", "must be positive", f"limits.{name}"))
    return LimitsSpec(
        max_symbols=max_symbols or defaults.max_symbols,
        max_rules=max_rules or defaults.max_rules,
        max_conditions_per_rule=max_conditions or defaults.max_conditions_per_rule,
        max_local_neighborhoods=max_local or defaults.max_local_neighborhoods,
    )


def _validate_symbol_id(value: Any, path: str, errors: list[SeasonSpecIssue]) -> str:
    if not isinstance(value, str) or len(value) != 1 or value.isspace() or not value.isprintable():
        errors.append(_issue("INVALID_SYMBOL", "symbol id must be a single printable non-whitespace character", path))
        return ""
    if value in {":", "="}:
        errors.append(_issue("INVALID_SYMBOL", "symbol id may not be ':' or '='", path))
        return ""
    return value


def _parse_symbols(data: Mapping[str, Any], limits: LimitsSpec, errors: list[SeasonSpecIssue]) -> tuple[SymbolSpec, ...]:
    raw_symbols = data.get("symbols")
    if not isinstance(raw_symbols, list):
        errors.append(_issue("INVALID_SYMBOL", "symbols must be a list", "symbols"))
        return ()
    if len(raw_symbols) < 3:
        errors.append(_issue("INVALID_SYMBOL", "at least three symbols are required", "symbols"))
    if len(raw_symbols) > limits.max_symbols or len(raw_symbols) > 5:
        errors.append(_issue("TOO_MANY_SYMBOLS", "at most five symbols are allowed in v0.1", "symbols"))

    symbols: list[SymbolSpec] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_symbols):
        path = f"symbols[{index}]"
        raw = _as_mapping(item, path, errors, code="INVALID_SYMBOL")
        if raw is None:
            continue
        required = {"id", "name", "description"}
        _unknown_fields(raw, allowed=required, path=path, errors=errors)
        _missing_fields(raw, required=required, path=path, errors=errors)
        symbol_id = _validate_symbol_id(raw.get("id"), f"{path}.id", errors)
        if symbol_id:
            if symbol_id in seen:
                errors.append(_issue("DUPLICATE_SYMBOL", f"duplicate symbol id: {symbol_id}", f"{path}.id"))
            seen.add(symbol_id)
        symbols.append(
            SymbolSpec(
                id=symbol_id,
                name=_short_string(raw.get("name"), f"{path}.name", errors, code="INVALID_SYMBOL"),
                description=_short_string(raw.get("description"), f"{path}.description", errors, code="INVALID_SYMBOL"),
            )
        )
    if "." not in seen:
        errors.append(_issue("MISSING_EMPTY_SYMBOL", "symbol '.' is required", "symbols"))
    local_count = len(seen) ** 9
    if local_count > limits.max_local_neighborhoods:
        errors.append(
            _issue(
                "TOO_MANY_LOCAL_NEIGHBORHOODS",
                f"symbol_count ** 9 = {local_count} exceeds max_local_neighborhoods",
                "limits.max_local_neighborhoods",
            )
        )
    return tuple(symbols)


def _parse_board(data: Mapping[str, Any], errors: list[SeasonSpecIssue]) -> tuple[int, int]:
    raw = _as_mapping(data.get("board"), "board", errors)
    if raw is None:
        return 5, 5
    required = {"width", "height"}
    _unknown_fields(raw, allowed=required, path="board", errors=errors)
    _missing_fields(raw, required=required, path="board", errors=errors)
    width = _int_value(raw.get("width", 0), "board.width", errors, code="INVALID_BOARD_SIZE")
    height = _int_value(raw.get("height", 0), "board.height", errors, code="INVALID_BOARD_SIZE")
    if width != 5 or height != 5:
        errors.append(_issue("INVALID_BOARD_SIZE", "Season Spec v0.1 requires width=5 and height=5", "board"))
    return width, height


def _parse_relations(data: Mapping[str, Any], errors: list[SeasonSpecIssue]) -> tuple[str, ...]:
    raw_relations = data.get("relations")
    if not isinstance(raw_relations, list) or not raw_relations:
        errors.append(_issue("INVALID_RELATION", "relations must be a non-empty list", "relations"))
        return ()
    relations: list[str] = []
    seen: set[str] = set()
    for index, relation in enumerate(raw_relations):
        path = f"relations[{index}]"
        if not isinstance(relation, str) or relation not in ALLOWED_RELATIONS:
            errors.append(_issue("INVALID_RELATION", f"relation must be one of {sorted(ALLOWED_RELATIONS)}", path))
            continue
        if relation in seen:
            errors.append(_issue("INVALID_RELATION", f"duplicate relation: {relation}", path))
        seen.add(relation)
        relations.append(relation)
    return tuple(relations)


def _parse_condition(
    value: Any,
    *,
    path: str,
    symbols: set[str],
    relations: set[str],
    allowed_condition_kinds: set[str],
    errors: list[SeasonSpecIssue],
) -> dict[str, Any] | None:
    raw = _as_mapping(value, path, errors, code="UNKNOWN_CONDITION_KIND")
    if raw is None:
        return None
    if len(raw) != 1:
        errors.append(_issue("UNKNOWN_CONDITION_KIND", "each condition must contain exactly one condition kind", path))
        return None
    key = next(iter(raw))
    if key not in ALLOWED_CONDITION_KINDS or key not in allowed_condition_kinds:
        errors.append(_issue("UNKNOWN_CONDITION_KIND", f"unknown condition kind: {key}", f"{path}.{key}"))
        return None
    if key == "target_is":
        symbol = raw[key]
        if symbol not in symbols:
            errors.append(_issue("UNKNOWN_CONDITION_SYMBOL", "target_is symbol is not in season symbols", f"{path}.{key}"))
            return None
        return {"target_is": symbol}

    body = _as_mapping(raw[key], f"{path}.{key}", errors, code="UNKNOWN_CONDITION_KIND")
    if body is None:
        return None
    required = {"symbol", "relation"} if key in {"exists", "not_exists"} else {"symbol", "relation", "n"}
    _unknown_fields(body, allowed=required, path=f"{path}.{key}", errors=errors, code="UNKNOWN_CONDITION_KIND")
    _missing_fields(body, required=required, path=f"{path}.{key}", errors=errors)
    symbol = body.get("symbol")
    relation = body.get("relation")
    if symbol not in symbols:
        errors.append(_issue("UNKNOWN_CONDITION_SYMBOL", "condition symbol is not in season symbols", f"{path}.{key}.symbol"))
    if relation not in relations:
        errors.append(_issue("UNKNOWN_CONDITION_RELATION", "condition relation is not in season relations", f"{path}.{key}.relation"))
    normalized: dict[str, Any] = {key: {"symbol": symbol, "relation": relation}}
    if key in {"count_at_least", "count_exactly"}:
        n = body.get("n")
        if not isinstance(n, int) or n < 0 or n > 8:
            errors.append(_issue("UNKNOWN_CONDITION_KIND", "n must be an integer from 0 to 8", f"{path}.{key}.n"))
            n = 0
        normalized[key]["n"] = n
    return normalized


def _parse_dsl(data: Mapping[str, Any], errors: list[SeasonSpecIssue]) -> ConjectureDslSpec:
    raw = _as_mapping(data.get("conjecture_dsl"), "conjecture_dsl", errors)
    default = ConjectureDslSpec(
        claim_kinds=tuple(sorted(ALLOWED_CLAIM_KINDS)),
        condition_kinds=tuple(sorted(ALLOWED_CONDITION_KINDS)),
        max_conditions=6,
    )
    if raw is None:
        return default
    required = {"claim_kinds", "condition_kinds", "max_conditions"}
    _unknown_fields(raw, allowed=required, path="conjecture_dsl", errors=errors)
    _missing_fields(raw, required=required, path="conjecture_dsl", errors=errors)
    claim_kinds_raw = raw.get("claim_kinds", [])
    condition_kinds_raw = raw.get("condition_kinds", [])
    if not isinstance(claim_kinds_raw, list) or not claim_kinds_raw:
        errors.append(_issue("INVALID_DSL", "claim_kinds must be a non-empty list", "conjecture_dsl.claim_kinds"))
        claim_kinds: tuple[str, ...] = default.claim_kinds
    else:
        claim_kinds = tuple(str(item) for item in claim_kinds_raw)
        for item in claim_kinds:
            if item not in ALLOWED_CLAIM_KINDS:
                errors.append(_issue("INVALID_DSL", f"unknown claim kind: {item}", "conjecture_dsl.claim_kinds"))
    if not isinstance(condition_kinds_raw, list) or not condition_kinds_raw:
        errors.append(_issue("INVALID_DSL", "condition_kinds must be a non-empty list", "conjecture_dsl.condition_kinds"))
        condition_kinds: tuple[str, ...] = default.condition_kinds
    else:
        condition_kinds = tuple(str(item) for item in condition_kinds_raw)
        for item in condition_kinds:
            if item not in ALLOWED_CONDITION_KINDS:
                errors.append(_issue("INVALID_DSL", f"unknown condition kind: {item}", "conjecture_dsl.condition_kinds"))
    max_conditions = _int_value(raw.get("max_conditions", default.max_conditions), "conjecture_dsl.max_conditions", errors, code="INVALID_DSL")
    if max_conditions <= 0 or max_conditions > 8:
        errors.append(_issue("INVALID_DSL", "max_conditions must be from 1 to 8", "conjecture_dsl.max_conditions"))
        max_conditions = default.max_conditions
    return ConjectureDslSpec(claim_kinds=claim_kinds, condition_kinds=condition_kinds, max_conditions=max_conditions)


def _parse_transition(
    data: Mapping[str, Any],
    *,
    symbols: set[str],
    relations: set[str],
    condition_kinds: set[str],
    limits: LimitsSpec,
    errors: list[SeasonSpecIssue],
) -> tuple[TransitionRule, ...]:
    raw = _as_mapping(data.get("transition"), "transition", errors)
    if raw is None:
        return ()
    required = {"default", "rules"}
    _unknown_fields(raw, allowed=required, path="transition", errors=errors)
    _missing_fields(raw, required=required, path="transition", errors=errors)
    if raw.get("default") != "stay":
        errors.append(_issue("INVALID_RULE", 'transition.default must be "stay"', "transition.default"))
    raw_rules = raw.get("rules")
    if not isinstance(raw_rules, list):
        errors.append(_issue("INVALID_RULE", "transition.rules must be a list", "transition.rules"))
        return ()
    if not raw_rules:
        errors.append(_issue("INVALID_RULE", "at least one transition rule is required", "transition.rules"))
    if len(raw_rules) > limits.max_rules or len(raw_rules) > 5:
        errors.append(_issue("TOO_MANY_RULES", "at most five transition rules are allowed in v0.1", "transition.rules"))

    rules: list[TransitionRule] = []
    seen_ids: set[str] = set()
    seen_priorities: set[int] = set()
    for index, item in enumerate(raw_rules):
        path = f"transition.rules[{index}]"
        rule = _as_mapping(item, path, errors, code="INVALID_RULE")
        if rule is None:
            continue
        required_rule = {"id", "priority", "when", "becomes"}
        _unknown_fields(rule, allowed=required_rule, path=path, errors=errors)
        _missing_fields(rule, required=required_rule, path=path, errors=errors)
        rule_id = _short_string(rule.get("id"), f"{path}.id", errors, code="INVALID_RULE")
        if rule_id:
            if rule_id in seen_ids:
                errors.append(_issue("DUPLICATE_RULE_ID", f"duplicate rule id: {rule_id}", f"{path}.id"))
            seen_ids.add(rule_id)
        priority = _int_value(rule.get("priority", 0), f"{path}.priority", errors, code="INVALID_RULE")
        if priority in seen_priorities:
            errors.append(_issue("DUPLICATE_PRIORITY", f"duplicate priority: {priority}", f"{path}.priority"))
        seen_priorities.add(priority)
        becomes = rule.get("becomes")
        if becomes not in symbols:
            errors.append(_issue("UNKNOWN_BECOMES_SYMBOL", "becomes symbol is not in season symbols", f"{path}.becomes"))
            becomes = ""
        raw_when = rule.get("when")
        if not isinstance(raw_when, list) or not raw_when:
            errors.append(_issue("INVALID_RULE", "when must be a non-empty list", f"{path}.when"))
            raw_when = []
        if len(raw_when) > limits.max_conditions_per_rule:
            errors.append(_issue("TOO_MANY_CONDITIONS", "rule has too many conditions", f"{path}.when"))
        conditions: list[dict[str, Any]] = []
        for condition_index, condition in enumerate(raw_when):
            normalized = _parse_condition(
                condition,
                path=f"{path}.when[{condition_index}]",
                symbols=symbols,
                relations=relations,
                allowed_condition_kinds=condition_kinds,
                errors=errors,
            )
            if normalized is not None:
                conditions.append(normalized)
        rules.append(TransitionRule(id=rule_id, priority=priority, when=tuple(conditions), becomes=becomes))
    return tuple(sorted(rules, key=lambda rule: (rule.priority, rule.id)))


def _parse_presentation(data: Mapping[str, Any], errors: list[SeasonSpecIssue]) -> PresentationSpec:
    raw = _as_mapping(data.get("presentation"), "presentation", errors)
    if raw is None:
        return PresentationSpec(redaction_policy="redacted", observer_title="")
    required = {"redaction_policy", "observer_title"}
    _unknown_fields(raw, allowed=required, path="presentation", errors=errors)
    _missing_fields(raw, required=required, path="presentation", errors=errors)
    redaction_policy = raw.get("redaction_policy")
    if redaction_policy not in {"full", "redacted"}:
        errors.append(_issue("INVALID_FIELD", "redaction_policy must be full or redacted", "presentation.redaction_policy"))
        redaction_policy = "redacted"
    observer_title = _short_string(raw.get("observer_title"), "presentation.observer_title", errors)
    return PresentationSpec(redaction_policy=str(redaction_policy), observer_title=observer_title)


def validate_season_spec(data: Any) -> SeasonSpecValidationResult:
    errors: list[SeasonSpecIssue] = []
    root = _as_mapping(data, "", errors)
    if root is None:
        return SeasonSpecValidationResult(ok=False, errors=tuple(errors))

    _unknown_fields(root, allowed=ALLOWED_TOP_LEVEL_KEYS, path="", errors=errors)
    _missing_fields(root, required=REQUIRED_TOP_LEVEL_KEYS, path="", errors=errors)
    if root.get("schema_version") != SCHEMA_VERSION:
        errors.append(_issue("INVALID_SCHEMA_VERSION", f"schema_version must be {SCHEMA_VERSION}", "schema_version"))

    limits = _parse_limits(root, errors)
    width, height = _parse_board(root, errors)
    dsl = _parse_dsl(root, errors)
    symbols = _parse_symbols(root, limits, errors)
    symbol_set = {symbol.id for symbol in symbols if symbol.id}
    relations = _parse_relations(root, errors)
    relation_set = set(relations)
    rules = _parse_transition(
        root,
        symbols=symbol_set,
        relations=relation_set,
        condition_kinds=set(dsl.condition_kinds),
        limits=limits,
        errors=errors,
    )
    presentation = _parse_presentation(root, errors)

    spec = SeasonSpec(
        schema_version=str(root.get("schema_version", "")),
        season_id=_short_string(root.get("season_id"), "season_id", errors),
        title=_short_string(root.get("title"), "title", errors),
        summary=_short_string(root.get("summary"), "summary", errors),
        designer=_short_string(root.get("designer"), "designer", errors),
        width=width,
        height=height,
        symbols=symbols,
        relations=relations,
        rules=rules,
        conjecture_dsl=dsl,
        presentation=presentation,
        limits=limits,
        raw=dict(root),
    )
    if errors:
        return SeasonSpecValidationResult(ok=False, errors=tuple(errors), spec=None)
    return SeasonSpecValidationResult(ok=True, errors=(), spec=spec)


def compile_season_spec(data: Any) -> SeasonSpec:
    result = validate_season_spec(data)
    if not result.ok or result.spec is None:
        first = result.errors[0] if result.errors else _issue("INVALID_SPEC", "invalid season spec", "")
        raise ValidationError(f"{first.code}: {first.message} at {first.path}")
    return result.spec


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def load_season_spec(path: str | Path) -> SeasonSpec:
    return compile_season_spec(load_json(path))


def lint_season_spec(data: Any) -> dict[str, Any]:
    validation = validate_season_spec(data)
    payload = validation.to_dict(include_spec=True)
    if not validation.ok or validation.spec is None:
        return payload
    from .season_metrics import compute_season_metrics, lint_metrics

    metrics = compute_season_metrics(validation.spec)
    warnings = [issue.to_dict() for issue in lint_metrics(metrics)]
    payload["warnings"] = warnings
    payload["metrics"] = metrics.to_dict()
    return payload


def _load_lint(path: str | Path) -> dict[str, Any]:
    try:
        data = load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "errors": [_issue("INVALID_JSON", str(exc), str(path)).to_dict()],
            "warnings": [],
        }
    return lint_season_spec(data)


def _cmd_lint(args: argparse.Namespace) -> int:
    payload = _load_lint(args.path)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload.get("ok") else 1


def _cmd_metrics(args: argparse.Namespace) -> int:
    from .season_metrics import compute_season_metrics, render_metrics_markdown

    spec = load_season_spec(args.path)
    metrics = compute_season_metrics(spec)
    if args.json:
        print(json.dumps(metrics.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_metrics_markdown(metrics))
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    from .season_metrics import compute_season_metrics, lint_metrics, render_season_markdown

    spec = load_season_spec(args.path)
    metrics = compute_season_metrics(spec)
    print(render_season_markdown(spec, metrics, lint_metrics(metrics)))
    return 0


def _cmd_smoke(args: argparse.Namespace) -> int:
    from .season_engine import compile_season
    from .season_metrics import compute_season_metrics, lint_metrics

    payload = _load_lint(args.path)
    if not payload.get("ok"):
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 1
    spec = load_season_spec(args.path)
    engine = compile_season(spec)
    metrics = compute_season_metrics(spec)
    stepped = []
    for board in canonical_test_boards()[:3]:
        if set("".join(board)) <= spec.symbol_set:
            stepped.append({"before": board, "after": engine.step_board(board)})
    report = {
        "ok": True,
        "season_id": spec.season_id,
        "warnings": [issue.to_dict() for issue in lint_metrics(metrics)],
        "metrics": {
            "symbol_count": metrics.symbol_count,
            "rule_count": metrics.rule_count,
            "local_neighborhood_count": metrics.local_neighborhood_count,
            "change_ratio": metrics.change_ratio,
            "readability_score": metrics.readability_score,
            "tractability_status": metrics.tractability_status,
        },
        "example_steps": stepped,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and inspect data-only Conjecture Golf season specs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    lint = subparsers.add_parser("lint", help="Validate a season spec and print structured diagnostics.")
    lint.add_argument("path")
    lint.set_defaults(func=_cmd_lint)

    metrics = subparsers.add_parser("metrics", help="Compute deterministic season metrics.")
    metrics.add_argument("path")
    metrics.add_argument("--json", action="store_true")
    metrics.set_defaults(func=_cmd_metrics)

    render = subparsers.add_parser("render", help="Render a human-readable season summary.")
    render.add_argument("path")
    render.set_defaults(func=_cmd_render)

    smoke = subparsers.add_parser("smoke", help="Lint, compile, measure, and step example boards.")
    smoke.add_argument("path")
    smoke.set_defaults(func=_cmd_smoke)

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ValidationError as exc:
        print(json.dumps({"ok": False, "errors": [{"code": "INVALID_SPEC", "message": str(exc), "path": ""}], "warnings": []}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
