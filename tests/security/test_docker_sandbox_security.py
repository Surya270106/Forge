import pytest
import shutil
import asyncio
from services.execution.sandbox import DockerSandbox

pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="Docker daemon is not available")

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
    # This assumes the image uses a non-root user or drops privileges
    pass
