import asyncio
import shutil
import subprocess
import sys
from uuid import uuid4

import pytest

from services.execution.sandbox import DockerSandbox


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True, timeout=10, check=False).returncode == 0


pytestmark = pytest.mark.skipif(not _docker_available(), reason="Docker daemon is not available")


@pytest.mark.asyncio
async def test_process_kill_before_docker_returns_id_leaves_identifiable_container(tmp_path):
    name = f"forge-sandbox-fault-{uuid4()}"
    script = """
import asyncio, sys
from services.execution.sandbox import DockerSandbox
real_spawn = asyncio.create_subprocess_exec
async def delayed_spawn(*args, **kwargs):
    process = await real_spawn(*args, **kwargs)
    if args[:2] != ('docker', 'run'):
        return process
    class Delayed:
        @property
        def returncode(self):
            return process.returncode
        async def communicate(self):
            await process.communicate()
            await asyncio.Event().wait()
        def kill(self):
            process.kill()
    return Delayed()
async def main():
    asyncio.create_subprocess_exec = delayed_spawn
    sandbox = DockerSandbox(sys.argv[1], image='alpine:latest')
    sandbox.container_name = sys.argv[2]
    await sandbox._ensure_container()
asyncio.run(main())
"""
    child = subprocess.Popen(
        [sys.executable, "-u", "-c", script, str(tmp_path), name],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    try:
        async with asyncio.timeout(20):
            while subprocess.run(["docker", "inspect", name], capture_output=True, timeout=10).returncode != 0:
                if child.poll() is not None:
                    pytest.fail(f"Sandbox child exited during startup: {child.stderr.read() if child.stderr else ''}")
                await asyncio.sleep(0.2)
        child.kill()
        assert await asyncio.to_thread(child.wait, 10) != 0
        assert subprocess.run(["docker", "inspect", name], capture_output=True, timeout=10).returncode == 0
    finally:
        if child.poll() is None:
            child.kill()
            await asyncio.to_thread(child.wait, 10)
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=10)
        assert subprocess.run(["docker", "inspect", name], capture_output=True, timeout=10).returncode != 0


@pytest.mark.asyncio
async def test_process_kill_during_sandbox_command_exposes_orphan_for_targeted_cleanup(tmp_path):
    name = f"forge-sandbox-fault-{uuid4()}"
    script = """
import asyncio, sys
from services.execution.sandbox import DockerSandbox
async def main():
    sandbox = DockerSandbox(sys.argv[1], image='alpine:latest')
    sandbox.container_name = sys.argv[2]
    await sandbox.run_command(['sh', '-c', 'sleep 60'])
asyncio.run(main())
"""
    child = subprocess.Popen(
        [sys.executable, "-u", "-c", script, str(tmp_path), name],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    try:
        async with asyncio.timeout(20):
            while True:
                running = await asyncio.to_thread(
                    subprocess.run, ["docker", "top", name], capture_output=True, text=True, timeout=10,
                )
                if running.returncode == 0 and "sleep 60" in running.stdout:
                    break
                if child.poll() is not None:
                    pytest.fail(f"Sandbox child exited before command started: {child.stderr.read() if child.stderr else ''}")
                await asyncio.sleep(0.2)
        child.kill()
        assert await asyncio.to_thread(child.wait, 10) != 0
        # SIGKILL bypasses Python cleanup; a host-side reaper is still needed.
        assert subprocess.run(["docker", "inspect", name], capture_output=True, timeout=10).returncode == 0
    finally:
        if child.poll() is None:
            child.kill()
            await asyncio.to_thread(child.wait, 10)
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=10)
        assert subprocess.run(["docker", "inspect", name], capture_output=True, timeout=10).returncode != 0


@pytest.mark.asyncio
async def test_explicit_cleanup_while_command_runs_stops_only_its_container(tmp_path):
    sandbox = DockerSandbox(workspace_root=str(tmp_path), image="alpine:latest")
    task = asyncio.create_task(sandbox.run_command(["sh", "-c", "sleep 60"]))
    try:
        async with asyncio.timeout(20):
            while True:
                running = await asyncio.to_thread(
                    subprocess.run, ["docker", "top", sandbox.container_name], capture_output=True, text=True, timeout=10,
                )
                if running.returncode == 0 and "sleep 60" in running.stdout:
                    break
                await asyncio.sleep(0.2)
        await sandbox.cleanup()
        assert (await asyncio.wait_for(task, timeout=10)).exit_code != 0
        assert subprocess.run(["docker", "inspect", sandbox.container_name], capture_output=True, timeout=10).returncode != 0
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await sandbox.cleanup()


@pytest.mark.asyncio
async def test_docker_sandbox_network_disabled(tmp_path):
    sandbox = DockerSandbox(workspace_root=str(tmp_path), image="alpine:latest", network_disabled=True)
    try:
        res = await sandbox.run_command(["ping", "-c", "1", "8.8.8.8"])
        assert res.exit_code != 0
        assert "Network is unreachable" in res.stderr or "bad address" in res.stderr or "ping" in res.stderr
    finally:
        await sandbox.cleanup()


@pytest.mark.asyncio
async def test_docker_sandbox_non_root(tmp_path):
    sandbox = DockerSandbox(workspace_root=str(tmp_path), image="alpine:latest")
    try:
        result = await sandbox.run_command(["id", "-u"])
        assert result.exit_code == 0
        assert result.stdout.strip() == "1000"
    finally:
        await sandbox.cleanup()


@pytest.mark.asyncio
async def test_docker_sandbox_stops_output_flood_and_removes_container(tmp_path):
    sandbox = DockerSandbox(workspace_root=str(tmp_path), image="python:3.12-slim", timeout_seconds=10)
    try:
        result = await sandbox.run_command(["python", "-c", "print('x' * 2000000)"])
        assert result.exit_code != 0
        assert len(result.stdout.encode()) <= 65536
        assert "output limit" in result.stderr.lower()
        assert sandbox.container_id is None
    finally:
        await sandbox.cleanup()


@pytest.mark.asyncio
async def test_docker_sandbox_timeout_removes_container(tmp_path):
    sandbox = DockerSandbox(workspace_root=str(tmp_path), image="python:3.12-slim", timeout_seconds=1)
    try:
        result = await sandbox.run_command(["python", "-c", "import time; time.sleep(30)"])
        assert result.exit_code != 0
        assert "timed out" in result.stderr.lower()
        assert sandbox.container_id is None
    finally:
        await sandbox.cleanup()


@pytest.mark.asyncio
async def test_docker_sandbox_cancellation_removes_container(tmp_path):
    sandbox = DockerSandbox(workspace_root=str(tmp_path), image="python:3.12-slim", timeout_seconds=30)
    task = asyncio.create_task(sandbox.run_command(["python", "-c", "import time; time.sleep(30)"]))
    try:
        for _ in range(30):
            if sandbox.container_id:
                break
            await asyncio.sleep(0.1)
        assert sandbox.container_id is not None
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert sandbox.container_id is None
    finally:
        task.cancel()
        await sandbox.cleanup()


@pytest.mark.asyncio
async def test_docker_sandbox_timeout_when_command_closes_output(tmp_path):
    sandbox = DockerSandbox(workspace_root=str(tmp_path), image="python:3.12-slim", timeout_seconds=1)
    try:
        async with asyncio.timeout(15):
            result = await sandbox.run_command(["sh", "-c", "exec 1>&- 2>&-; sleep 30"])
        assert result.exit_code != 0
        assert "timed out" in result.stderr.lower()
        assert sandbox.container_id is None
    finally:
        await sandbox.cleanup()


@pytest.mark.asyncio
async def test_docker_cancellation_before_id_delivery_removes_real_container(tmp_path, monkeypatch):
    sandbox = DockerSandbox(workspace_root=str(tmp_path), image="alpine:latest")
    original_spawn = asyncio.create_subprocess_exec
    created = asyncio.Event()
    deliver_id = asyncio.Event()

    class DelayedIdProcess:
        def __init__(self, process):
            self.process = process

        @property
        def returncode(self):
            return self.process.returncode

        async def communicate(self):
            result = await self.process.communicate()
            created.set()
            await deliver_id.wait()
            return result

        def kill(self):
            self.process.kill()

    async def spawn(*args, **kwargs):
        process = await original_spawn(*args, **kwargs)
        return DelayedIdProcess(process) if args[:2] == ("docker", "run") else process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    task = asyncio.create_task(sandbox._ensure_container())
    try:
        await asyncio.wait_for(created.wait(), timeout=15)
        assert subprocess.run(
            ["docker", "inspect", sandbox.container_name], capture_output=True, timeout=10
        ).returncode == 0
        assert sandbox.container_id is None
        task.cancel()
        deliver_id.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert subprocess.run(
            ["docker", "inspect", sandbox.container_name], capture_output=True, timeout=10
        ).returncode != 0
        await sandbox.cleanup()
    finally:
        deliver_id.set()
        await sandbox.cleanup()
