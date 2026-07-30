import os
import shutil

import pytest

from services.execution.git_client import GitClient
from services.execution.sandbox import LocalProcessSandbox


@pytest.fixture
def workspace_root(tmp_path):
    root = tmp_path / "forge_test_workspace"
    root.mkdir()
    yield str(root)
    # Cleanup
    shutil.rmtree(root, ignore_errors=True)


@pytest.mark.asyncio
async def test_sandbox_path_validation(workspace_root):
    sandbox = LocalProcessSandbox(workspace_root)

    # Valid write
    await sandbox.write_file("test.txt", b"hello world")
    assert os.path.exists(os.path.join(workspace_root, "test.txt"))

    # Path traversal attempt should raise PermissionError
    with pytest.raises(PermissionError):
        await sandbox.write_file("../escape.txt", b"hacked")

    with pytest.raises(PermissionError):
        await sandbox.read_file("../escape.txt")


@pytest.mark.asyncio
async def test_sandbox_command_execution(workspace_root):
    sandbox = LocalProcessSandbox(workspace_root)

    # Depending on OS, 'echo' might be a shell builtin so we use python
    result = await sandbox.run_command(["python", "-c", "print('sandbox_test')"])
    assert result.exit_code == 0
    assert "sandbox_test" in result.stdout


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
@pytest.mark.asyncio
async def test_git_client_isolation(workspace_root):
    sandbox = LocalProcessSandbox(workspace_root)
    git = GitClient(sandbox)

    # Config git temporarily to avoid author errors in test
    await sandbox.run_command(["git", "config", "--global", "user.email", "test@forge.com"])
    await sandbox.run_command(["git", "config", "--global", "user.name", "Test"])

    init_res = await git.init()
    assert init_res.exit_code == 0

    # Add a file
    await sandbox.write_file("code.py", b"print('V1')")
    await git.add("code.py")

    commit_res = await git.commit("Initial commit")
    assert commit_res.exit_code == 0

    status_res = await git.status()
    assert status_res.stdout.strip() == ""  # Clean tree
