import os
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from bench.private.solutions import deterministic_edits
from services.bench.dataset import load_suite
from services.bench.fixture import materialize_fixture
from services.bench.grader import grade_candidate
from services.execution.sandbox import DockerSandbox


@pytest.mark.asyncio
async def test_private_grader_wins_over_candidate_shadow_and_workspace_is_read_only():
    root = os.environ.get("FORGE_BENCH_WORKSPACE_ROOT")
    if not root or subprocess.run(["docker", "info"], capture_output=True, timeout=10).returncode:
        pytest.skip("Shared Docker workspace and socket required")
    task = load_suite().tasks[0]
    workspace = Path(root) / "grader-isolation" / str(uuid4())
    materialize_fixture(workspace, task.base_commit)
    for path, content in deterministic_edits(task.id, "incorrect"):
        (workspace / path).write_text(content)
    (workspace / "test_cases.py").write_text("# Candidate-controlled shadow grader\n")
    (workspace / "forgebench.py").chmod(0o666)
    sandbox = DockerSandbox(str(workspace), image="python:3.12-slim", read_only_workspace=True)
    try:
        result = await sandbox.run_command(["sh", "-c", "echo tampered > /workspace/forgebench.py"])
        assert result.exit_code != 0
    finally:
        await sandbox.cleanup()
    graded = await grade_candidate(task, workspace)
    assert next(check for check in graded["checks"] if check["category"] == "correctness")["status"] == "failed"
    assert next(check for check in graded["checks"] if check["category"] == "quality")["status"] == "failed"
    assert "tampered" not in (workspace / "forgebench.py").read_text()
