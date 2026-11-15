import asyncio
import sys
from unittest.mock import AsyncMock

import pytest

from services.execution.sandbox import DockerSandbox, LocalProcessSandbox


def test_local_sandbox_stops_output_flood(tmp_path):
    sandbox = LocalProcessSandbox(str(tmp_path), timeout_seconds=10)
    result = asyncio.run(
        sandbox.run_command([sys.executable, "-c", "print('x' * 2000000)"])
    )

    assert result.exit_code != 0
    assert len(result.stdout.encode()) <= 65536
    assert "output limit" in result.stderr.lower()


def test_local_sandbox_preserves_small_output(tmp_path):
    sandbox = LocalProcessSandbox(str(tmp_path), timeout_seconds=10)
    result = asyncio.run(sandbox.run_command([sys.executable, "-c", "print('ok')"]))

    assert result.exit_code == 0
    assert result.stdout.strip() == "ok"


def test_local_sandbox_stops_stderr_flood(tmp_path):
    sandbox = LocalProcessSandbox(str(tmp_path), timeout_seconds=10)
    result = asyncio.run(
        sandbox.run_command([sys.executable, "-c", "import sys; sys.stderr.write('x' * 2000000)"])
    )

    assert result.exit_code != 0
    assert len(result.stderr.encode()) <= 65536
    assert "output limit" in result.stderr.lower()


def test_local_sandbox_timeout_still_returns_failure(tmp_path):
    sandbox = LocalProcessSandbox(str(tmp_path), timeout_seconds=1)
    result = asyncio.run(sandbox.run_command([sys.executable, "-c", "import time; time.sleep(30)"]))

    assert result.exit_code != 0
    assert "timed out" in result.stderr.lower()


@pytest.mark.asyncio
async def test_docker_sandbox_cancellation_during_startup_removes_container(tmp_path, monkeypatch):
    sandbox = DockerSandbox(str(tmp_path))
    started = asyncio.Event()

    async def start_container():
        sandbox.container_id = "started-container"
        started.set()
        await asyncio.Event().wait()

    async def cleanup():
        sandbox.container_id = None

    cleanup_spy = AsyncMock(side_effect=cleanup)
    monkeypatch.setattr(sandbox, "_ensure_container", start_container)
    monkeypatch.setattr(sandbox, "cleanup", cleanup_spy)
    task = asyncio.create_task(sandbox.run_command(["true"]))
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    cleanup_spy.assert_awaited_once()
    assert sandbox.container_id is None


@pytest.mark.asyncio
async def test_docker_startup_cancellation_before_id_waits_then_cleans_up(tmp_path, monkeypatch):
    sandbox = DockerSandbox(str(tmp_path))
    started = asyncio.Event()
    finish_startup = asyncio.Event()

    class StartingDocker:
        returncode = None

        async def communicate(self):
            started.set()
            await finish_startup.wait()
            self.returncode = 0
            return b"created-container", b""

    async def create_process(*_args, **_kwargs):
        return StartingDocker()

    async def cleanup():
        sandbox.container_id = None

    cleanup_spy = AsyncMock(side_effect=cleanup)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    monkeypatch.setattr(sandbox, "cleanup", cleanup_spy)
    task = asyncio.create_task(sandbox._ensure_container())
    await started.wait()
    task.cancel()
    finish_startup.set()

    with pytest.raises(asyncio.CancelledError):
        await task
    cleanup_spy.assert_awaited_once()
    assert sandbox.container_id is None


@pytest.mark.asyncio
async def test_docker_cleanup_finishes_after_cancellation(tmp_path, monkeypatch):
    sandbox = DockerSandbox(str(tmp_path))
    sandbox.container_id = "created-container"
    removing = asyncio.Event()
    finish_removal = asyncio.Event()

    class RemovingDocker:
        returncode = None

        async def communicate(self):
            removing.set()
            await finish_removal.wait()
            self.returncode = 0
            return b"created-container", b""

    async def create_process(*_args, **_kwargs):
        return RemovingDocker()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    task = asyncio.create_task(sandbox.cleanup())
    await removing.wait()
    task.cancel()
    finish_removal.set()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert sandbox.container_id is None
