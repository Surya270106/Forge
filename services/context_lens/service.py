"""Bounded, content-free change and verification evidence."""

import re
from collections.abc import Sequence
from pathlib import PurePosixPath

from services.safety.policy import _protected_path

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def capture_file_changes(mutations: list) -> list[dict]:
    if len(mutations) > 50:
        raise ValueError("Patch exceeds Context Lens file limit")
    changes = []
    for mutation in mutations:
        path = mutation.file_path
        if _protected_path(path) or PurePosixPath(path).as_posix() != path:
            raise ValueError("Protected patch path")
        hunks = []
        additions = deletions = 0
        for line in mutation.diff_hunk.splitlines():
            match = HUNK.match(line)
            if match:
                hunks.append({"before_start": int(match[1]), "before_count": int(match[2] or 1),
                              "after_start": int(match[3]), "after_count": int(match[4] or 1)})
            elif line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1
        if not hunks:
            raise ValueError("Patch has no changed regions")
        kind = {"CREATE": "added", "DELETE": "deleted", "UPDATE": "modified"}.get(mutation.mutation_type, "unknown")
        changes.append({"mutation_id": str(mutation.id), "execution_id": str(mutation.execution_job_id),
                        "task_node_id": str(mutation.task_node_id), "path": path, "type": kind,
                        "hunks": hunks, "additions": additions, "deletions": deletions})
    return changes


def verification_summary(results: Sequence, relevant_test_count: int) -> dict:
    statuses = [getattr(result.status, "value", result.status) for result in results]
    return {"relevant_tests": relevant_test_count, "selected_tests": None,
            "executed_commands": sum(status in {"PASSED", "FAILED", "WARNING"} for status in statuses),
            "passed_commands": statuses.count("PASSED"), "failed_commands": statuses.count("FAILED"),
            "skipped_commands": statuses.count("SKIPPED"), "relevant_tests_executed": None,
            "coverage_claimed": False}


def approval_evidence(patch, current_digest: str | None, captured_digest: str | None = None) -> dict:
    status = getattr(patch.status, "value", patch.status)
    current = bool(patch.review_digest and current_digest == patch.review_digest
                   and (captured_digest is None or captured_digest == patch.review_digest))
    approved = status in {"ACCEPTED", "COMMITTED", "PULL_REQUEST_CREATED"} and current and patch.reviewed_by is not None
    publication = ("published" if patch.publish_status == "SUCCEEDED" and status == "PULL_REQUEST_CREATED"
                   and bool(patch.pull_request_url) else
                   "failed" if patch.publish_status == "FAILED" else
                   "requested" if patch.publish_status in {"QUEUED", "RUNNING"} else "not_requested")
    return {"status": status, "review_digest": patch.review_digest, "current": current,
            "approved": approved, "reviewer_id": str(patch.reviewed_by) if patch.reviewed_by else None,
            "reviewed_at": patch.reviewed_at.isoformat() if patch.reviewed_at else None,
            "publication": publication, "pull_request_url": patch.pull_request_url if publication == "published" else None}
