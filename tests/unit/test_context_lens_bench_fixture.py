"""Deterministic Context Lens evidence assertions on Forge Bench's pinned source fixture."""

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from services.atlas.graph import build_graph, impact, scan_repository
from services.context_lens.service import approval_evidence, capture_file_changes, verification_summary


def test_bench_retry_change_has_structural_impact_but_no_invented_verification():
    root = Path(__file__).resolve().parents[2] / "bench" / "fixture"
    graph = build_graph(scan_repository(root).facts)
    downstream = impact(graph, ["symbol:forgebench.py:function:retry_delay"])
    assert any(item.key == "symbol:worker.py:function:retry_schedule" and item.depth == 1
               and item.via[0].confidence == "HIGH" for item in downstream.items)

    mutation = SimpleNamespace(id=uuid4(), execution_job_id=uuid4(), task_node_id=uuid4(),
                               file_path="forgebench.py", mutation_type="UPDATE",
                               diff_hunk="--- forgebench.py\n+++ forgebench.py\n@@ -1 +1 @@\n-old\n+new\n")
    change = capture_file_changes([mutation])[0]
    assert change["path"] == "forgebench.py" and "old" not in str(change)
    no_results = verification_summary([], relevant_test_count=1)
    assert no_results["relevant_tests"] == 1 and no_results["executed_commands"] == 0
    assert no_results["relevant_tests_executed"] is None and not no_results["coverage_claimed"]


def test_bench_evidence_distinguishes_failure_skip_and_stale_approval():
    results = [SimpleNamespace(status="FAILED"), SimpleNamespace(status="SKIPPED")]
    summary = verification_summary(results, relevant_test_count=2)
    assert summary["executed_commands"] == 1 and summary["failed_commands"] == 1
    assert summary["skipped_commands"] == 1 and summary["selected_tests"] is None
    patch = SimpleNamespace(status="ACCEPTED", review_digest="a" * 64, reviewed_by=uuid4(),
                            reviewed_at=None, publish_status="FAILED", pull_request_url=None)
    review = approval_evidence(patch, "b" * 64)
    assert not review["approved"] and not review["current"] and review["publication"] == "failed"
