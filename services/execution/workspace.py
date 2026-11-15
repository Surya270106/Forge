"""Deterministic, isolated Git worktrees for execution attempts."""

import hashlib
import os
import subprocess
from pathlib import Path
from uuid import UUID


def execution_workspace_path(root: str, organization_id: UUID, repository_id: UUID, job_id: UUID, attempt: int = 0) -> Path:
    if attempt < 0:
        raise ValueError("Invalid execution attempt")
    return Path(root, ".forge-executions", str(job_id), str(attempt))


def _git(workspace: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={workspace.as_posix()}", "-C", str(workspace), *args],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if result.returncode:
        raise RuntimeError("Execution workspace Git operation failed")
    return result.stdout.strip()


def workspace_change_fingerprint(workspace: str | Path) -> str:
    """Fingerprint reviewable repository changes, including untracked file contents."""
    root = Path(workspace).resolve()
    result = subprocess.run(
        ["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root),
         "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        capture_output=True, timeout=30, check=True,
    )
    digest = hashlib.sha256(result.stdout)
    records = iter(filter(None, result.stdout.split(b"\0")))
    for record in records:
        path = root / record[3:].decode("utf-8", errors="surrogateescape")
        if b"R" in record[:2] or b"C" in record[:2]:
            digest.update(next(records))  # old path in Git's -z rename format
        if path.is_symlink():
            digest.update(os.fsencode(os.readlink(path)))
        elif path.is_file():
            with path.open("rb") as source:
                digest.update(hashlib.file_digest(source, "sha256").digest())
        else:
            digest.update(b"deleted")
    return digest.hexdigest()


def prepare_execution_workspace(
    root: str, organization_id: UUID, repository_id: UUID, job_id: UUID, base_sha: str, attempt: int = 0
) -> Path:
    source = Path(root, str(organization_id), str(repository_id)).resolve()
    target = execution_workspace_path(root, organization_id, repository_id, job_id, attempt).resolve()
    if not source.is_dir() or _git(source, "rev-parse", "HEAD") != base_sha:
        raise RuntimeError("Imported repository base is unavailable or changed")
    if target.exists():
        common_dir = Path(_git(target, "rev-parse", "--git-common-dir")).resolve()
        if common_dir != (source / ".git").resolve() or _git(target, "rev-parse", "HEAD") != base_sha:
            raise RuntimeError("Execution workspace conflicts with existing files")
        if _git(target, "status", "--porcelain"):
            raise RuntimeError("Execution workspace contains prior changes")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    _git(source, "-c", "core.hooksPath=/dev/null", "worktree", "add", "--detach", str(target), base_sha)
    return target
