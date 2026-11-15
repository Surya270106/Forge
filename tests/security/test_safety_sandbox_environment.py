import asyncio
import sys

import pytest

from services.execution.sandbox import DockerSandbox, LocalProcessSandbox


@pytest.mark.asyncio
async def test_agent_sandboxes_reject_unenforced_network_and_secret_environment(tmp_path):
    with pytest.raises(PermissionError):
        await DockerSandbox(str(tmp_path), network_disabled=False)._ensure_container()
    with pytest.raises(PermissionError):
        await DockerSandbox(str(tmp_path)).run_command(["true"], env={"DATABASE_URL": "secret"})


def test_local_development_sandbox_does_not_inherit_forge_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_SECRET_TEST", "do-not-leak")
    sandbox = LocalProcessSandbox(str(tmp_path))
    result = asyncio.run(sandbox.run_command([sys.executable, "-c",
        "import os; print(os.getenv('FORGE_SECRET_TEST', 'absent'))"]))
    assert result.exit_code == 0
    assert result.stdout.strip() == "absent"
