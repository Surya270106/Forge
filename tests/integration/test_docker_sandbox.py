import shutil
import subprocess

import pytest

from services.execution.sandbox import DockerSandbox


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True, timeout=10, check=False).returncode == 0


pytestmark = pytest.mark.skipif(not _docker_available(), reason="Docker daemon is not available")


@pytest.mark.asyncio
async def test_docker_sandbox_python_execution(tmp_path):
    sandbox = DockerSandbox(workspace_root=str(tmp_path), image="python:3.12-slim")
    try:
        res = await sandbox.run_command(["python", "-c", "print('Hello Docker')"])
        assert res.exit_code == 0
        assert "Hello Docker" in res.stdout
    finally:
        await sandbox.cleanup()
