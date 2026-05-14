from conjecture_golf.obligations import (
    ObligationLedger,
    all_local_obligation_ids,
    obligation_id,
    obligation_ids_for_conjecture,
    parse_obligation_id,
    summarize_obligation_ids,
)


TRUE_FLOWER = {
    "player": "blue",
    "name": "flower_growth",
    "if": [
        {"target_is": "."},
        {"exists": {"symbol": "W", "relation": "diagonal"}},
        {"exists": {"symbol": "F", "relation": "orthogonal"}},
        {"not_exists": {"symbol": "S", "relation": "king"}},
    ],
    "then": {"target_becomes": "F"},
}

STONE_EQUIVALENCE = {
    "player": "stone",
    "name": "stone_stays_stone_exactly",
    "claim_kind": "equivalence",
    "if": [{"target_is": "S"}],
    "then": {"target_becomes": "S"},
}

STONE_NECESSARY = {
    "player": "stone",
    "name": "stone_output_requires_stone_input",
    "claim_kind": "necessary",
    "if": [{"target_is": "S"}],
    "then": {"target_becomes": "S"},
}


def test_obligation_id_is_stable_and_readable():
    identifier = (
        obligation_id(
            world_version="season_0",
            center_before_symbol=".",
            center_after_symbol="F",
            local_neighborhood_index=42,
            claim_kind="sufficient",
        )
    )
    assert identifier == "season_0:claim=sufficient:before=.:after=F:local=000042"
    parsed = parse_obligation_id(identifier)
    assert parsed["claim"] == "sufficient"
    assert parsed["before"] == "."
    assert parsed["after"] == "F"
    assert parsed["local_index"] == 42


def test_obligation_ids_for_conjecture_are_deterministic():
    first = obligation_ids_for_conjecture(TRUE_FLOWER)
    second = obligation_ids_for_conjecture(TRUE_FLOWER)

    assert first == second
    assert len(first) > 0
    assert all(item.startswith("season_0:claim=sufficient:") for item in first)


def test_obligation_ledger_splits_new_and_stale_coverage():
    obligations = obligation_ids_for_conjecture(TRUE_FLOWER)
    ledger = ObligationLedger()

    first = ledger.measure(obligations)
    ledger.mark(first)
    second = ledger.measure(obligations)

    assert first.new_obligations == obligations
    assert not first.stale_obligations
    assert not second.new_obligations
    assert second.stale_obligations == obligations


def test_equivalence_coverage_subsumes_necessary_side():
    equivalence_obligations = obligation_ids_for_conjecture(STONE_EQUIVALENCE)
    necessary_obligations = obligation_ids_for_conjecture(STONE_NECESSARY)

    assert necessary_obligations < equivalence_obligations


def test_universe_and_summary_split_claim_sides():
    universe = all_local_obligation_ids()
    summary = summarize_obligation_ids(universe)

    assert len(universe) > 0
    assert summary["total"] == len(universe)
    assert summary["by_claim_kind"]["sufficient"] == summary["by_claim_kind"]["necessary"]
