"""Atlas conformance checks on Forge Bench's pinned fixture source."""

from pathlib import Path

from services.atlas.graph import build_graph, impact, scan_repository


def test_bench_fixture_import_call_and_impact_evidence():
    root = Path(__file__).resolve().parents[2] / "bench" / "fixture"
    graph = build_graph(scan_repository(root).facts)
    assert any(edge.kind == "IMPORTS" and edge.source == "file:worker.py"
               and edge.target == "file:forgebench.py" and edge.resolution == "RESOLVED_STATIC"
               for edge in graph.edges)
    assert any(edge.kind == "CALLS" and edge.source == "symbol:worker.py:function:retry_schedule"
               and edge.target == "symbol:forgebench.py:function:retry_delay"
               and edge.evidence_path == "worker.py" and edge.evidence_line == 5
               for edge in graph.edges)
    result = impact(graph, ["symbol:forgebench.py:function:retry_delay"])
    assert any(item.key == "symbol:worker.py:function:retry_schedule" for item in result.items)
