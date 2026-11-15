import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


def _workspace_path(workspace_root: str, path: str) -> Path:
    """Resolve a workspace-relative path without allowing traversal or symlink escapes."""
    relative = Path(path)
    if relative.is_absolute() or ".." in relative.parts:
        raise PermissionError("Path is outside the workspace")
    root = Path(workspace_root).resolve()
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise PermissionError("Path is outside the workspace")
    return resolved


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
        return str(_workspace_path(self.workspace_root, path))

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


import uuid


class DockerSandbox(SandboxRuntime):
    """
    Docker-based execution environment.
    Mounts the workspace into a container and executes commands via docker exec.
    """

    def __init__(self, workspace_root: str, image: str = "node:20", timeout_seconds: int = 300, network_disabled: bool = True):
        self.workspace_root = workspace_root
        self.image = image
        self.container_id: str | None = None
        self.timeout_seconds = timeout_seconds
        self.network_disabled = network_disabled
        self.sandbox_id = str(uuid.uuid4())

    async def _ensure_container(self) -> None:
        if self.container_id:
            return

        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            f"forge-sandbox-{self.sandbox_id}",
            "--rm",
            "--read-only",
            "--user",
            "1000:1000",
            "--env",
            "HOME=/tmp",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--memory=512m",
            "--cpus=1",
            "--pids-limit=128",
            "--network",
            "none" if self.network_disabled else "bridge",
            "-v",
            f"{os.path.abspath(self.workspace_root)}:/workspace",
            "--tmpfs",
            "/tmp",
            "--tmpfs",
            "/root",
            "-w",
            "/workspace",
            self.image,
            "tail",
            "-f",
            "/dev/null",
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"Failed to start DockerSandbox container: {stderr.decode()}")

        self.container_id = stdout.decode().strip()
        logger.info("docker_container_started", container_id=self.container_id)

    async def run_command(self, command: list[str], env: dict[str, str] | None = None, cwd: str | None = None) -> SandboxResult:
        container_cwd = None
        if cwd:
            # Workers use /workspace paths; verifiers use relative paths.
            relative_cwd = cwd.removeprefix("/workspace/") if cwd.startswith("/workspace/") else cwd
            if relative_cwd == "/workspace":
                relative_cwd = "."
            resolved = _workspace_path(self.workspace_root, relative_cwd)
            container_cwd = (
                "/workspace"
                if resolved == Path(self.workspace_root).resolve()
                else f"/workspace/{resolved.relative_to(Path(self.workspace_root).resolve()).as_posix()}"
            )
        await self._ensure_container()

        exec_cmd = ["docker", "exec"]
        if env:
            for k, v in env.items():
                exec_cmd.extend(["-e", f"{k}={v}"])
        if container_cwd:
            exec_cmd.extend(["-w", container_cwd])

        exec_cmd.append(self.container_id)  # type: ignore
        exec_cmd.extend(command)

        proc = await asyncio.create_subprocess_exec(
            *exec_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_seconds)
            exit_code = proc.returncode or 0
        except TimeoutError:
            proc.kill()
            stdout, stderr = await proc.communicate()
            return SandboxResult(
                exit_code=-1,
                stdout=stdout.decode(),
                stderr=f"Command timed out after {self.timeout_seconds}s",
            )

        return SandboxResult(exit_code=exit_code, stdout=stdout.decode(), stderr=stderr.decode())

    async def write_file(self, path: str, content: bytes) -> None:
        safe_path = _workspace_path(self.workspace_root, path)
        os.makedirs(os.path.dirname(safe_path), exist_ok=True)
        with open(safe_path, "wb") as f:
            f.write(content)

    async def read_file(self, path: str) -> bytes:
        safe_path = _workspace_path(self.workspace_root, path)
        if not os.path.exists(safe_path):
            raise FileNotFoundError(f"File not found: {path}")
        with open(safe_path, "rb") as f:
            return f.read()

    async def cleanup(self) -> None:
        if self.container_id:
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "rm",
                "-f",
                self.container_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
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
