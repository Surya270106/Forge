import os
import subprocess
from pathlib import Path

import pytest

from bench.private.solutions import deterministic_edits
from services.bench.dataset import load_suite
from services.bench.fixture import materialize_fixture


@pytest.mark.parametrize("task", load_suite().tasks, ids=lambda task: task.id)
def test_deterministic_plan_passes_independent_checks(task, tmp_path):
    workspace = tmp_path / "fixture"
    materialize_fixture(workspace, task.base_commit)
    for path, content in deterministic_edits(task.id):
        (workspace / path).write_text(content)
    for check in task.checks:
        if check["type"] != "unittest":
            continue
        env = {**os.environ, "PYTHONPATH": os.pathsep.join([
            str(Path(__file__).resolve().parents[2] / "bench" / "private"), str(workspace)])}
        result = subprocess.run(["python", "-B", "-m", "unittest", "-q", f"test_cases.{check['case']}"],
                                cwd=workspace, env=env, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("variant,failed_category", [("incorrect", "correctness"), ("regression", "regression")])
def test_bad_demo_variants_fail_real_hidden_checks(variant, failed_category, tmp_path):
    task = load_suite().tasks[0]
    workspace = tmp_path / "fixture"
    materialize_fixture(workspace, task.base_commit)
    for path, content in deterministic_edits(task.id, variant):
        (workspace / path).write_text(content)
    check = next(check for check in task.checks if check["category"] == failed_category)
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(Path(__file__).resolve().parents[2] / "bench" / "private"), str(workspace)])}
    result = subprocess.run(["python", "-B", "-m", "unittest", "-q", f"test_cases.{check['case']}"],
                            cwd=workspace, env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
