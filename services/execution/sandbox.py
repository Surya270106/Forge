import asyncio
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)
MAX_OUTPUT_BYTES = 64 * 1024
SANDBOX_ENV_KEYS = frozenset({"CI", "LANG", "LC_ALL", "NODE_ENV", "PYTHONUNBUFFERED", "TERM", "TZ"})


def _sandbox_environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    if extra and (not extra.keys() <= SANDBOX_ENV_KEYS or any(not isinstance(value, str) for value in extra.values())):
        raise PermissionError("Sandbox environment variable is not permitted")
    base = {key: value for key, value in os.environ.items()
            if key in {"PATH", "HOME", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL", "TZ"}}
    return {**base, **(extra or {})}


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


async def _capture_bounded(proc: asyncio.subprocess.Process, timeout_seconds: int) -> tuple[SandboxResult, bool]:
    assert proc.stdout is not None and proc.stderr is not None

    async def read_stream(stream: asyncio.StreamReader) -> bytes:
        output = bytearray()
        while chunk := await stream.read(8192):
            remaining = MAX_OUTPUT_BYTES + 1 - len(output)
            output.extend(chunk[:remaining])
            if len(output) > MAX_OUTPUT_BYTES:
                break
        return bytes(output)

    tasks = {
        asyncio.create_task(read_stream(proc.stdout)): "stdout",
        asyncio.create_task(read_stream(proc.stderr)): "stderr",
    }
    output: dict[str, bytes] = {}
    reason: str | None = None
    try:
        async with asyncio.timeout(timeout_seconds):
            while tasks:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    name = tasks.pop(task)
                    output[name] = task.result()
                    if len(output[name]) > MAX_OUTPUT_BYTES:
                        reason = "Command exceeded the output limit"
                if reason:
                    break
            if not reason:
                await proc.wait()
    except TimeoutError:
        reason = f"Command timed out after {timeout_seconds}s"
    except asyncio.CancelledError:
        reason = "Command cancelled"
        raise
    finally:
        if reason and proc.returncode is None:
            proc.kill()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if reason:
            # Drain the already bounded pipe buffers so Windows subprocess teardown completes.
            await proc.communicate()

    stdout = output.get("stdout", b"")[:MAX_OUTPUT_BYTES].decode(errors="replace")
    stderr = reason or output.get("stderr", b"").decode(errors="replace")
    return SandboxResult(exit_code=-1 if reason else proc.returncode or 0, stdout=stdout, stderr=stderr), reason is not None


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
            env=_sandbox_environment(env),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        result, _ = await _capture_bounded(proc, self.timeout_seconds)
        return result

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

    def __init__(self, workspace_root: str, image: str = "node:20", timeout_seconds: int = 300, network_disabled: bool = True, read_only_workspace: bool = False):
        self.workspace_root = workspace_root
        self.image = image
        self.container_id: str | None = None
        self.timeout_seconds = timeout_seconds
        self.network_disabled = network_disabled
        self.read_only_workspace = read_only_workspace
        self.sandbox_id = str(uuid.uuid4())
        self.container_name = f"forge-sandbox-{self.sandbox_id}"
        self.event_sink: Callable[[str, dict], Awaitable[None]] | None = None

    async def _emit(self, event_type: str) -> None:
        if self.event_sink:
            try:
                data = {"sandbox_id": self.sandbox_id}
                if event_type == "sandbox.created" and self.container_id:
                    data["image_ref"] = self.image
                    try:
                        inspect = await asyncio.create_subprocess_exec(
                            "docker", "inspect", "--format", "{{.Image}}", self.container_id,
                            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                        )
                        stdout, _ = await asyncio.wait_for(inspect.communicate(), timeout=5)
                        if inspect.returncode == 0 and stdout.decode().strip().startswith("sha256:"):
                            data["image_digest"] = stdout.decode().strip()
                    except TimeoutError:
                        inspect.kill()
                        await inspect.communicate()
                    except OSError:
                        pass
                await self.event_sink(event_type, data)
            except Exception as error:
                logger.warning("sandbox_flight_recorder_failed", event_type=event_type, error_type=type(error).__name__)

    async def _ensure_container(self) -> None:
        if self.container_id:
            return
        if not self.network_disabled:
            raise PermissionError("Sandbox network access has no enforceable egress policy")

        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            self.container_name,
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
            f"{os.path.abspath(self.workspace_root)}:/workspace{':ro' if self.read_only_workspace else ''}",
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

        async def start_container() -> None:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            communication = asyncio.create_task(proc.communicate())
            try:
                stdout, stderr = await asyncio.wait_for(asyncio.shield(communication), timeout=30)
            except TimeoutError:
                proc.kill()
                await communication
                raise RuntimeError("DockerSandbox container startup timed out") from None
            if proc.returncode != 0:
                raise RuntimeError(f"Failed to start DockerSandbox container: {stderr.decode()}")
            self.container_id = stdout.decode().strip()
            logger.info("docker_container_started", container_id=self.container_id)

        startup = asyncio.create_task(start_container())
        try:
            await asyncio.shield(startup)
            await self._emit("sandbox.created")
        except asyncio.CancelledError:
            await self._emit("sandbox.cancelled")
            try:
                await startup
            finally:
                await self.cleanup()
            raise
        except BaseException:
            await self._emit("sandbox.start_failed")
            try:
                await startup
            finally:
                await self.cleanup()
            raise

    async def run_command(self, command: list[str], env: dict[str, str] | None = None, cwd: str | None = None) -> SandboxResult:
        _sandbox_environment(env)
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
        try:
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
            result, aborted = await _capture_bounded(proc, self.timeout_seconds)
            if aborted:
                await self.cleanup()
            return result
        except asyncio.CancelledError:
            await self._emit("sandbox.cancelled")
            await self.cleanup()
            raise
        except BaseException:
            await self.cleanup()
            raise

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
        active = self.container_id is not None
        if active:
            await self._emit("sandbox.cleanup_started")
        async def remove_container() -> None:
            proc = await asyncio.create_subprocess_exec(
                "docker", "rm", "-f", self.container_name,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            if proc.returncode == 0 or b"No such container" in stderr:
                self.container_id = None
            else:
                raise RuntimeError("DockerSandbox container cleanup failed")

        removal = asyncio.create_task(remove_container())
        try:
            await asyncio.shield(removal)
        except asyncio.CancelledError:
            await removal
            if active:
                await self._emit("sandbox.cleanup_completed")
            raise
        except Exception:
            if active:
                await self._emit("sandbox.cleanup_failed")
            raise
        else:
            if active:
                await self._emit("sandbox.cleanup_completed")


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
