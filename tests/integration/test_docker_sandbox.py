import pytest
import shutil
import asyncio
from services.execution.sandbox import DockerSandbox

pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="Docker daemon is not available")

@pytest.mark.asyncio
async def test_docker_sandbox_python_execution(tmp_path):
    sandbox = DockerSandbox(workspace_root=str(tmp_path), image="python:3.12-slim")
    try:
        res = await sandbox.run_command(["python", "-c", "print('Hello Docker')"])
        assert res.exit_code == 0
        assert "Hello Docker" in res.stdout
    finally:
        await sandbox.cleanup()
