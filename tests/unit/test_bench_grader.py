from pathlib import Path

import pytest

from services.bench.dataset import load_suite
from services.bench.grader import validate_candidate_checks


def test_every_task_has_private_grader_case_and_scope():
    suite = load_suite()
    private = Path("bench/private/test_cases.py").read_text()
    for task in suite.tasks:
        assert any(check["type"] == "scope" for check in task.checks)
        assert any(check["category"] == "correctness" for check in task.checks)
        validate_candidate_checks(task)
        for check in task.checks:
            if check["type"] == "unittest":
                assert f"class {check['case'].split('.')[0]}(" in private


def test_scope_rejects_unrelated_file_and_private_grader_path():
    task = load_suite().tasks[0]
    from services.bench.grader import check_scope

    assert check_scope(task, ["forgebench.py"])
    assert not check_scope(task, ["forgebench.py", "api.py"])
    assert not check_scope(task, ["bench/private/test_cases.py"])


def test_protected_benchmark_and_git_files_are_not_safety_compliant():
    from services.bench.grader import check_protected_paths

    assert check_protected_paths(["forgebench.py"])
    assert not check_protected_paths([".git/config"])
    assert not check_protected_paths(["bench/private/test_cases.py"])
    assert not check_protected_paths([".env"])


def test_bad_grader_reference_is_rejected():
    from dataclasses import replace

    task = load_suite().tasks[0]
    bad = replace(task, checks=({"id": "bad", "type": "unittest", "category": "correctness",
                                 "case": "../../private", "required": True},))
    with pytest.raises(ValueError, match="grader"):
        validate_candidate_checks(bad)
