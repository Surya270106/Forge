from uuid import uuid4

from services.context_lens.service import approval_evidence, capture_file_changes, verification_summary


def test_capture_file_changes_keeps_hunk_ranges_and_operation_provenance_without_source():
    mutation = type("Mutation", (), {
        "id": uuid4(), "execution_job_id": uuid4(), "task_node_id": uuid4(),
        "file_path": "src/example.py", "mutation_type": "UPDATE",
        "diff_hunk": "--- src/example.py\n+++ src/example.py\n@@ -2,2 +2,3 @@\n-old-secret\n+new-secret\n context\n+added\n",
    })()
    changes = capture_file_changes([mutation])
    assert changes == [{
        "mutation_id": str(mutation.id), "execution_id": str(mutation.execution_job_id),
        "task_node_id": str(mutation.task_node_id), "path": "src/example.py", "type": "modified",
        "hunks": [{"before_start": 2, "before_count": 2, "after_start": 2, "after_count": 3}],
        "additions": 2, "deletions": 1,
    }]
    assert "secret" not in str(changes)


def test_empty_file_hunk_does_not_claim_file_creation_or_deletion():
    mutation = type("Mutation", (), {"id": uuid4(), "execution_job_id": uuid4(), "task_node_id": uuid4(),
                                     "file_path": "src/empty.py", "mutation_type": "UPDATE",
                                     "diff_hunk": "--- src/empty.py\n+++ src/empty.py\n@@ -0,0 +1 @@\n+value\n"})()
    assert capture_file_changes([mutation])[0]["type"] == "modified"


def test_verification_summary_does_not_turn_relevant_tests_into_executed_tests():
    results = [type("Result", (), {"status": status})() for status in ("PASSED", "FAILED", "SKIPPED")]
    summary = verification_summary(results, relevant_test_count=4)
    assert summary == {"relevant_tests": 4, "selected_tests": None, "executed_commands": 2,
                       "passed_commands": 1, "failed_commands": 1, "skipped_commands": 1,
                       "relevant_tests_executed": None, "coverage_claimed": False}


def test_approval_and_publication_require_current_digest_and_completed_result():
    patch = type("Patch", (), {"status": "ACCEPTED", "review_digest": "a" * 64,
                                 "reviewed_by": uuid4(), "reviewed_at": None,
                                 "publish_status": "QUEUED", "pull_request_url": None})()
    assert approval_evidence(patch, "b" * 64)["current"] is False
    assert approval_evidence(patch, "a" * 64)["publication"] == "requested"
    assert approval_evidence(patch, "a" * 64, "b" * 64)["approved"] is False
    patch.publish_status = "SUCCEEDED"
    assert approval_evidence(patch, "a" * 64)["publication"] != "published"
    patch.pull_request_url = "https://github.com/example/repo/pull/1"
    patch.status = "PULL_REQUEST_CREATED"
    assert approval_evidence(patch, "a" * 64)["publication"] == "published"
    assert approval_evidence(patch, "b" * 64)["approved"] is False
    assert approval_evidence(patch, "b" * 64)["publication"] == "published"
