"""Exercise command interruption and targeted cleanup against a real local Docker daemon."""

import asyncio
import os
import subprocess

import pytest

from services.execution.sandbox import DockerSandbox


@pytest.mark.asyncio
async def test_cancelled_command_removes_only_its_sandbox(tmp_path):
    if os.getenv("FORGE_REQUIRE_DOCKER_CANCEL") != "1":
        pytest.skip("Disposable Docker daemon access required")
    sandbox = DockerSandbox(str(tmp_path), image="node:20-slim")
    command = asyncio.create_task(sandbox.run_command(["sh", "-c", "sleep 30"], cwd="/workspace"))
    try:
        async with asyncio.timeout(15):
            while sandbox.container_id is None:
                if command.done():
                    await command
                await asyncio.sleep(0.1)
        await asyncio.sleep(0.2)
        command.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(command, timeout=15)
        result = subprocess.run(["docker", "inspect", sandbox.container_name],
                                capture_output=True, text=True, timeout=10)
        assert result.returncode != 0
        assert sandbox.container_id is None
    finally:
        if not command.done():
            command.cancel()
            with pytest.raises(asyncio.CancelledError):
                await command
        await sandbox.cleanup()
