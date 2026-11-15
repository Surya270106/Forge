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
