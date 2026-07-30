from .sandbox import SandboxResult, SandboxRuntime


class GitClient:
    """
    Sandboxed Git operations. All operations execute strictly within the isolated workspace boundary.
    """

    def __init__(self, sandbox: SandboxRuntime):
        self.sandbox = sandbox

    async def init(self) -> SandboxResult:
        return await self.sandbox.run_command(["git", "init"])

    async def add(self, path: str = ".") -> SandboxResult:
        return await self.sandbox.run_command(["git", "add", path])

    async def commit(self, message: str) -> SandboxResult:
        return await self.sandbox.run_command(["git", "commit", "-m", message])

    async def checkout(self, branch: str, create: bool = False) -> SandboxResult:
        cmd = ["git", "checkout"]
        if create:
            cmd.append("-b")
        cmd.append(branch)
        return await self.sandbox.run_command(cmd)

    async def status(self) -> SandboxResult:
        return await self.sandbox.run_command(["git", "status", "--porcelain"])

    async def apply_patch(self, patch_content: bytes) -> SandboxResult:
        # Write patch file
        await self.sandbox.write_file(".forge-temp.patch", patch_content)
        # Apply patch
        result = await self.sandbox.run_command(["git", "apply", ".forge-temp.patch"])
        # Cleanup
        await self.sandbox.run_command(["rm", "-f", ".forge-temp.patch"])
        return result
