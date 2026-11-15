import pytest

from services.bench.dataset import load_suite
from services.bench.scoring import compare_results, score_trial, summarize_trials


def test_suite_digest_is_stable_and_private_checks_are_hidden():
    suite = load_suite()
    assert len(suite.tasks) >= 10
    assert suite.digest == load_suite().digest
    assert all(task.base_commit and task.instruction and task.checks for task in suite.tasks)
    assert all("checks" not in task.public() for task in suite.tasks)


def test_correctness_gate_prevents_fast_incorrect_solution_from_passing():
    checks = [
        {"id": "required", "category": "correctness", "status": "failed", "required": True},
        {"id": "regression", "category": "regression", "status": "passed", "required": True},
    ]
    result = score_trial(checks, {"duration_ms": 10, "token_count": None})
    assert result["passed"] is False
    assert result["score"] < 50
    assert result["metrics"]["token_count"] is None


def test_identical_evidence_scores_identically_and_comparison_requires_same_dataset():
    checks = [{"id": "required", "category": "correctness", "status": "passed", "required": True}]
    left = score_trial(checks, {"duration_ms": 100})
    assert left == score_trial(checks, {"duration_ms": 100})
    with pytest.raises(ValueError, match="dataset"):
        compare_results({"dataset_digest": "a", "score": 80}, {"dataset_digest": "b", "score": 90})


def test_failed_agent_trial_counts_as_zero_but_infrastructure_outage_is_separate():
    trials = [
        {"status": "PASSED", "result": {"score": 90, "breakdown": {"correctness": 100},
                                        "metrics": {"duration_ms": 100, "token_count": None}}},
        {"status": "FAILED", "result": None, "failure_category": "agent"},
        {"status": "ERROR", "result": None, "failure_category": "infrastructure"},
    ]
    summary = summarize_trials(trials)
    assert summary["score"] == 45
    assert summary["score_denominator"] == 2
    assert summary["success_rate"] == 0.5
    assert summary["infrastructure_error_count"] == 1
    assert summary["average_token_count"] is None
