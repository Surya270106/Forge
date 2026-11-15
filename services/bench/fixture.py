"""Materialize the immutable fixture base in the worker's shared workspace."""

import os
import shutil
import subprocess
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[2] / "bench" / "fixture"
FILES = ("README.md", "api.py", "forgebench.py", "worker.py")


def _git(target: Path, *args: str, env: dict | None = None) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={target.as_posix()}", "-c", "core.autocrlf=false",
         "-C", str(target), *args],
        capture_output=True, text=True, timeout=30, check=True, env=env,
    )
    return result.stdout.strip()


def materialize_fixture(target: Path, expected_commit: str) -> str:
    if target.is_symlink():
        raise ValueError("Fixture workspace is a symlink")
    target = target.resolve()
    if target.exists():
        try:
            commit = _git(target, "rev-parse", "HEAD")
            clean = not _git(target, "status", "--porcelain", "--untracked-files=all")
        except (OSError, subprocess.SubprocessError) as error:
            raise ValueError("Existing fixture workspace is not a repository") from error
        if commit != expected_commit or not clean:
            raise ValueError("Existing fixture workspace changed")
        return commit
    target.mkdir(parents=True)
    for name in FILES:
        shutil.copyfile(FIXTURE / name, target / name)
    _git(target, "init", "-q")
    _git(target, "add", *FILES)
    _git(target, "update-index", "--chmod=-x", *FILES)
    environment = {**os.environ, "GIT_AUTHOR_DATE": "2024-01-01T00:00:00Z",
                   "GIT_COMMITTER_DATE": "2024-01-01T00:00:00Z"}
    _git(target, "-c", "user.name=Forge Bench", "-c", "user.email=bench@forge.invalid",
         "commit", "-q", "-m", "Forge Bench v1 fixture", env=environment)
    commit = _git(target, "rev-parse", "HEAD")
    if commit != expected_commit:
        raise ValueError("Fixture files do not match the pinned revision")
    return commit
