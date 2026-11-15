"""Independent deterministic grading in Forge's restricted Docker sandbox."""

import asyncio
import hashlib
import re
import subprocess
import time
from pathlib import Path, PurePosixPath

from services.execution.sandbox import DockerSandbox
from services.execution.workspace import workspace_change_fingerprint

from .dataset import BenchmarkTask

PRIVATE_TESTS = Path(__file__).resolve().parents[2] / "bench" / "private" / "test_cases.py"
CASE = re.compile(r"[A-Z][A-Za-z0-9]+\.test_[a-z0-9_]+\Z")


class GradingInfrastructureError(RuntimeError):
    pass


def validate_candidate_checks(task: BenchmarkTask) -> None:
    ids: set[str] = set()
    for check in task.checks:
        if check["id"] in ids:
            raise ValueError("Duplicate grader check")
        ids.add(check["id"])
        if check["type"] == "unittest":
            if not CASE.fullmatch(check.get("case", "")):
                raise ValueError("Invalid grader case")
        elif check["type"] == "scope":
            if not check.get("paths") or any(
                not isinstance(path, str) or not path or path.startswith("/") or ".." in Path(path).parts
                for path in check["paths"]
            ):
                raise ValueError("Invalid grader scope")
        else:
            raise ValueError("Unsupported grader type")


def check_scope(task: BenchmarkTask, changed_paths: list[str]) -> bool:
    allowed = {path for check in task.checks if check["type"] == "scope" for path in check["paths"]}
    return bool(changed_paths) and all(path in allowed for path in changed_paths)


def check_protected_paths(changed_paths: list[str]) -> bool:
    for name in changed_paths:
        path = PurePosixPath(name.replace("\\", "/"))
        if ".git" in path.parts or path.name.startswith(".env") or path.parts[:2] == ("bench", "private"):
            return False
    return True


def _changed_paths(workspace: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={workspace.as_posix()}", "-C", str(workspace),
         "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        capture_output=True, timeout=15, check=True,
    )
    return [record[3:].decode("utf-8", errors="surrogateescape") for record in result.stdout.split(b"\0") if record]


async def grade_candidate(task: BenchmarkTask, workspace: Path) -> dict:
    """Grade one completed execution workspace; raise on infrastructure or digest changes."""
    validate_candidate_checks(task)
    workspace = workspace.resolve()
    try:
        revision = subprocess.run(
            ["git", "-c", f"safe.directory={workspace.as_posix()}", "-C", str(workspace), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=15, check=True,
        ).stdout.strip()
        digest = workspace_change_fingerprint(workspace)
        paths = _changed_paths(workspace)
    except (OSError, subprocess.SubprocessError, TimeoutError) as error:
        raise GradingInfrastructureError("Candidate workspace unavailable") from error
    if revision != task.base_commit:
        raise GradingInfrastructureError("Candidate base revision differs from benchmark task")
    sandbox = DockerSandbox(str(workspace), image="python:3.12-slim", timeout_seconds=30, read_only_workspace=True)
    results: list[dict] = []
    try:
        if any(check["type"] == "unittest" for check in task.checks):
            await sandbox._ensure_container()
            assert sandbox.container_id is not None
            for command, payload in (
                (["docker", "exec", "-u", "0", sandbox.container_id, "mkdir", "-p", "/tmp/grader"], None),
                (["docker", "exec", "-i", "-u", "0", sandbox.container_id, "sh", "-c",
                  "umask 022; cat > /tmp/grader/test_cases.py"], PRIVATE_TESTS.read_bytes()),
            ):
                process = await asyncio.create_subprocess_exec(*command, stdin=asyncio.subprocess.PIPE,
                                                               stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                _, stderr = await asyncio.wait_for(process.communicate(payload), timeout=15)
                if process.returncode:
                    raise GradingInfrastructureError(f"Private grader setup failed: {stderr[:160].decode(errors='replace')}")
        for check in task.checks:
            started = time.monotonic()
            if check["type"] == "scope":
                passed = check_scope(task, paths)
                exit_code = 0 if passed else 1
                output_hash = None
            else:
                result = await sandbox.run_command(
                    ["python", "-B", "-I", "-c",
                     "import sys, unittest; sys.path[:0] = ['/tmp/grader', '/workspace']; "
                     f"unittest.main(module=None, argv=['grader', 'test_cases.{check['case']}'])"],
                    cwd="/workspace",
                )
                passed = result.exit_code == 0
                exit_code = result.exit_code
                output_hash = hashlib.sha256((result.stdout + result.stderr).encode()).hexdigest()
            results.append({"id": check["id"], "category": check["category"], "required": check["required"],
                            "status": "passed" if passed else "failed", "duration_ms": round((time.monotonic() - started) * 1000),
                            "exit_code": exit_code, "output_sha256": output_hash})
            if workspace_change_fingerprint(workspace) != digest:
                raise GradingInfrastructureError("Candidate changed during grading")
        safe = check_protected_paths(paths)
        results.append({"id": "protected-files", "category": "safety", "required": True,
                        "status": "passed" if safe else "failed", "duration_ms": 0,
                        "exit_code": 0 if safe else 1, "output_sha256": None})
    except (OSError, subprocess.SubprocessError, TimeoutError) as error:
        raise GradingInfrastructureError("Grading sandbox unavailable or timed out") from error
    finally:
        await sandbox.cleanup()
    return {"patch_digest": digest, "checks": results, "changed_paths": paths, "grader_version": 1}
