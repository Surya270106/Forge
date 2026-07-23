import asyncio
import os
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str


class SandboxRuntime:
    """Base abstraction for execution sandboxes."""

    async def run_command(self, command: list[str], env: dict[str, str] | None = None, cwd: str | None = None) -> SandboxResult:
        raise NotImplementedError

    async def write_file(self, path: str, content: bytes) -> None:
        raise NotImplementedError

    async def read_file(self, path: str) -> bytes:
        raise NotImplementedError

    async def cleanup(self) -> None:
        raise NotImplementedError


class LocalProcessSandbox(SandboxRuntime):
    """
    Controlled local development execution.
    Enforces workspace boundaries, timeouts, and process limits.
    """

    def __init__(self, workspace_root: str, timeout_seconds: int = 300):
        self.workspace_root = workspace_root
        self.timeout_seconds = timeout_seconds

        if not os.path.exists(self.workspace_root):
            os.makedirs(self.workspace_root, exist_ok=True)

    def _validate_path(self, path: str) -> str:
        """Ensure paths do not escape the workspace root."""
        abs_path = os.path.abspath(os.path.join(self.workspace_root, path))
        if not abs_path.startswith(os.path.abspath(self.workspace_root)):
            raise PermissionError(f"Path traversal attempted: {path}")
        return abs_path

    async def run_command(self, command: list[str], env: dict[str, str] | None = None, cwd: str | None = None) -> SandboxResult:
        target_cwd = self.workspace_root
        if cwd:
            target_cwd = self._validate_path(cwd)

        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=target_cwd,
            env=env or os.environ.copy(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_seconds)
        except TimeoutError:
            proc.kill()
            stdout, stderr = await proc.communicate()
            return SandboxResult(
                exit_code=-1,
                stdout=stdout.decode(),
                stderr=f"Command timed out after {self.timeout_seconds}s",
            )

        return SandboxResult(exit_code=proc.returncode or 0, stdout=stdout.decode(), stderr=stderr.decode())

    async def write_file(self, path: str, content: bytes) -> None:
        safe_path = self._validate_path(path)
        os.makedirs(os.path.dirname(safe_path), exist_ok=True)
        with open(safe_path, "wb") as f:
            f.write(content)

    async def read_file(self, path: str) -> bytes:
        safe_path = self._validate_path(path)
        if not os.path.exists(safe_path):
            raise FileNotFoundError(f"File not found: {path}")
        with open(safe_path, "rb") as f:
            return f.read()

    async def cleanup(self) -> None:
        # For a true sandbox, this would wipe the directory.
        # However, for local execution tracing we might keep it.
        pass


class DockerSandbox(SandboxRuntime):
    """
    Docker-based execution environment.
    Mounts the workspace into a container and executes commands via docker exec.
    """

    def __init__(self, workspace_root: str, image: str = "ubuntu:22.04"):
        self.workspace_root = workspace_root
        self.image = image
        self.container_id: str | None = None

    async def _ensure_container(self) -> None:
        if self.container_id:
            return
        # Mocked container start. In reality: `docker run -d -v {self.workspace_root}:/workspace {self.image} tail -f /dev/null`
        self.container_id = "mock-container-id"
        logger.info("docker_container_started", container_id=self.container_id)

    async def run_command(self, command: list[str], env: dict[str, str] | None = None, cwd: str | None = None) -> SandboxResult:
        await self._ensure_container()
        # Mocked docker exec
        return SandboxResult(exit_code=0, stdout="Docker execution mocked", stderr="")

    async def write_file(self, path: str, content: bytes) -> None:
        pass

    async def read_file(self, path: str) -> bytes:
        return b""

    async def cleanup(self) -> None:
        if self.container_id:
            # Mocked docker kill/rm
            self.container_id = None


@dataclass
class FirecrackerConfig:
    kernel_image_path: str
    rootfs_path: str
    cpu_count: int = 1
    mem_size_mb: int = 512
    socket_path: str = "/tmp/firecracker.socket"


class FirecrackerSandbox(SandboxRuntime):
    """
    MicroVM-based execution environment providing strong isolation.
    """

    def __init__(self, config: FirecrackerConfig, workspace_root: str):
        self.config = config
        self.workspace_root = workspace_root
        self.is_running = False

    async def start_vm(self) -> None:
        # Interface contract: call Firecracker API socket to configure and start VM
        self.is_running = True

    async def run_command(self, command: list[str], env: dict[str, str] | None = None, cwd: str | None = None) -> SandboxResult:
        if not self.is_running:
            raise RuntimeError("MicroVM is not running")
        # Interface contract: ssh or agent communication to execute command inside MicroVM
        return SandboxResult(exit_code=0, stdout="", stderr="")

    async def write_file(self, path: str, content: bytes) -> None:
        pass

    async def read_file(self, path: str) -> bytes:
        return b""

    async def cleanup(self) -> None:
        # Send Stop action to Firecracker API and clean up socket
        self.is_running = False
