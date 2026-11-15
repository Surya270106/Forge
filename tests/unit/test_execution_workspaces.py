import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from services.execution.workspace import prepare_execution_workspace, workspace_change_fingerprint


def _git(path, *args):
    return subprocess.run(["git", *args], cwd=path, check=True, capture_output=True, text=True, timeout=10).stdout.strip()


def test_concurrent_execution_workspaces_are_isolated(tmp_path):
    organization_id, repository_id, first_job, second_job = (uuid4() for _ in range(4))
    source = tmp_path / str(organization_id) / str(repository_id)
    source.mkdir(parents=True)
    _git(source, "init", "-b", "main")
    (source / "file.txt").write_text("base\n")
    _git(source, "add", "file.txt")
    _git(source, "-c", "user.name=Forge Test", "-c", "user.email=test@example.invalid", "commit", "-m", "base")
    base = _git(source, "rev-parse", "HEAD")

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(prepare_execution_workspace, str(tmp_path), organization_id, repository_id, first_job, base)
        second_future = executor.submit(prepare_execution_workspace, str(tmp_path), organization_id, repository_id, second_job, base)
        first, second = first_future.result(), second_future.result()
    assert prepare_execution_workspace(str(tmp_path), organization_id, repository_id, first_job, base) == first
    (first / "file.txt").write_text("first\n")

    assert first != second
    assert (source / "file.txt").read_text() == "base\n"
    assert (second / "file.txt").read_text() == "base\n"
    assert _git(first, "rev-parse", "HEAD") == base
    assert _git(second, "rev-parse", "HEAD") == base


def test_process_kill_after_git_worktree_add_can_reuse_clean_attempt(tmp_path):
    organization_id, repository_id, job_id = (uuid4() for _ in range(3))
    source = tmp_path / str(organization_id) / str(repository_id)
    source.mkdir(parents=True)
    _git(source, "init", "-b", "main")
    (source / "file.txt").write_text("base\n")
    _git(source, "add", "file.txt")
    _git(source, "-c", "user.name=Forge Test", "-c", "user.email=test@example.invalid", "commit", "-m", "base")
    base = _git(source, "rev-parse", "HEAD")
    marker = tmp_path / "added.marker"
    script = """
import subprocess, sys, time
from pathlib import Path
from uuid import UUID
from services.execution.workspace import prepare_execution_workspace
real_run = subprocess.run
def delayed_run(args, **kwargs):
    result = real_run(args, **kwargs)
    if 'worktree' in args and 'add' in args:
        Path(sys.argv[7]).write_text('registered')
        time.sleep(60)
    return result
subprocess.run = delayed_run
prepare_execution_workspace(sys.argv[1], UUID(sys.argv[2]), UUID(sys.argv[3]), UUID(sys.argv[4]), sys.argv[5], int(sys.argv[6]))
"""
    child = subprocess.Popen(
        [sys.executable, "-u", "-c", script, str(tmp_path), str(organization_id), str(repository_id),
         str(job_id), base, "1", str(marker)], stderr=subprocess.PIPE, text=True,
    )
    try:
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            assert child.poll() is None, child.stderr.read() if child.stderr else "Child exited"
            time.sleep(0.1)
        assert marker.read_text() == "registered"
        child.kill()
        assert child.wait(timeout=10) != 0
        attempt = prepare_execution_workspace(str(tmp_path), organization_id, repository_id, job_id, base, 1)
        assert _git(attempt, "rev-parse", "HEAD") == base
        assert _git(attempt, "status", "--porcelain") == ""
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)


def test_workspace_fingerprint_detects_command_edits_but_ignores_build_outputs(tmp_path):
    _git(tmp_path, "init", "-b", "main")
    (tmp_path / ".gitignore").write_text("build/\n")
    (tmp_path / "tracked.txt").write_text("base\n")
    _git(tmp_path, "add", ".gitignore", "tracked.txt")
    _git(tmp_path, "-c", "user.name=Forge Test", "-c", "user.email=test@example.invalid", "commit", "-m", "base")
    (tmp_path / "reviewable.txt").write_text("approved edit\n")
    before = workspace_change_fingerprint(tmp_path)
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "output.txt").write_text("generated\n")
    assert workspace_change_fingerprint(tmp_path) == before
    (tmp_path / "tracked.txt").write_text("command edit\n")
    assert workspace_change_fingerprint(tmp_path) != before
    (tmp_path / "tracked.txt").write_text("base\n")
    (tmp_path / "reviewable.txt").write_text("command changed approved edit\n")
    assert workspace_change_fingerprint(tmp_path) != before
    (tmp_path / "reviewable.txt").write_text("approved edit\n")
    (tmp_path / "new-source.txt").write_text("unreviewed\n")
    assert workspace_change_fingerprint(tmp_path) != before
