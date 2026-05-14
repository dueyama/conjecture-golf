from conjecture_golf.frontier import build_frontier_report_from_records, render_frontier_markdown


TRUE_FLOWER = {
    "type": "conjecture",
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


def test_frontier_report_summarizes_open_public_coverage():
    report = build_frontier_report_from_records([TRUE_FLOWER])
    markdown = render_frontier_markdown(report)

    assert report.covered_obligations > 0
    assert report.uncovered_obligations > 0
    assert report.open_frontier
    assert "Open Frontier" in markdown
    assert "local=" not in markdown
