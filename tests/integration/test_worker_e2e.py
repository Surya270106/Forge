"""Run the real worker and Docker sandbox against disposable local CI services."""

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import pytest
import redis.asyncio as redis_async
from redis.exceptions import ResponseError
from sqlalchemy import select

from packages.database.engine import dispose_engine, get_engine, get_session_factory
from packages.database.models.auth import OrganizationModel, RoleBindingModel, UserModel
from packages.database.models.execution import ExecutionStatus
from packages.database.models.outbox_event import OutboxEventModel
from packages.database.models.planning import PlanModel, PlanStatus, TaskEdgeModel, TaskNodeModel
from packages.database.models.processed_event import ProcessedEventModel
from packages.database.models.repository import RepositoryModel, RepositoryStatus
from packages.database.models.verification import VerificationJobModel, VerificationStatus
from packages.database.tenant import set_system_context
from services.auth.dependencies import _verify_and_set_tenant
from services.execution.api import get_execution_logs, get_execution_mutations, get_execution_status, start_execution
from services.execution.schemas import StartExecutionRequest
from services.verification.api import get_latest_verification


def _git(workspace: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={workspace.as_posix()}", *args],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode:
        raise AssertionError(f"Fixture Git command failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _fixture_repository(workspace: Path, language: str = "javascript") -> str:
    workspace.mkdir(parents=True)
    workspace.chmod(0o755)
    (workspace / "result.txt").write_text("original\n")
    (workspace / "forge.yaml").write_text(
        json.dumps(
            {
                "version": 1,
                "languages": [language],
                "verification": {
                    "test": [
                        {
                            "identifier": "fixture-result",
                            "display_name": "Fixture result",
                            "category": "test",
                            "command": (["python3", "-c", "import pathlib,sys; sys.exit(0 if pathlib.Path('result.txt').read_text().startswith('expected') else 1)"]
                                        if language == "python" else ["sh", "-c", "grep -q '^expected' result.txt"]),
                        }
                    ]
                },
            }
        )
    )
    _git(workspace, "init", "-b", "main")
    _git(workspace, "add", "result.txt", "forge.yaml")
    _git(workspace, "-c", "user.name=Forge CI", "-c", "user.email=forge-ci@example.invalid", "commit", "-m", "fixture")
    return _git(workspace, "rev-parse", "HEAD")


def _require_isolated_services() -> tuple[str, str]:
    if os.getenv("FORGE_REQUIRE_WORKER_E2E") != "1":
        pytest.skip("Set FORGE_REQUIRE_WORKER_E2E=1 with disposable local PostgreSQL, Redis, and Docker")
    database_url = os.getenv("DATABASE_URL", "")
    redis_url = os.getenv("REDIS_URL", "")
    database = urlsplit(database_url)
    cache = urlsplit(redis_url)
    if (
        database.hostname not in {"localhost", "127.0.0.1"}
        or not database.path.lstrip("/").startswith("forge_e2e_")
        or cache.hostname not in {"localhost", "127.0.0.1"}
        or database.username != "postgres"
    ):
        pytest.fail("Worker E2E requires local disposable PostgreSQL and Redis, and a forge_e2e_* database")
    return database_url, redis_url


async def _wait_for_worker(redis_client: redis_async.Redis, process: subprocess.Popen[str], log_path: Path, consumer_name: str) -> None:
    async with asyncio.timeout(30):
        while True:
            if process.poll() is not None:
                pytest.fail(f"Worker exited before queue registration:\n{log_path.read_text()[-4000:]}")
            try:
                consumers = await redis_client.xinfo_consumers("forge:events:execution", "forge_worker_group")
                if any(consumer["name"] == consumer_name.encode() for consumer in consumers):
                    return
            except ResponseError:
                pass
            await asyncio.sleep(0.1)


def _cleanup_owned_sandboxes(workspace_root: Path) -> None:
    """Remove only test sandboxes whose workspace mount is inside this test's root."""
    result = subprocess.run(
        ["docker", "ps", "-aq", "--filter", "name=forge-sandbox-"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    for container_id in result.stdout.splitlines():
        inspected = subprocess.run(
            ["docker", "inspect", "--format", "{{json .Mounts}}", container_id],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if inspected.returncode:
            if "no such object" in inspected.stderr.lower() or "no such container" in inspected.stderr.lower():
                continue  # Docker --rm removed it between ps and inspect.
            raise RuntimeError(f"Cannot inspect test sandbox {container_id}: {inspected.stderr.strip()}")
        mounts = json.loads(inspected.stdout)
        if any(
            mount.get("Destination") == "/workspace" and Path(mount.get("Source", "")).resolve().is_relative_to(workspace_root.resolve())
            for mount in mounts
        ):
            removed = subprocess.run(["docker", "rm", "-f", container_id], capture_output=True, text=True, timeout=10)
            if removed.returncode and "no such container" not in removed.stderr.lower():
                raise RuntimeError(f"Cannot remove test sandbox {container_id}: {removed.stderr.strip()}")


@pytest.mark.asyncio
async def test_worker_queue_sandbox_verification_and_authorized_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_url, redis_url = _require_isolated_services()
    subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], check=True, capture_output=True, timeout=10)
    workspace_root = tmp_path / "workspaces"
    workspace_root.mkdir()
    workspace_root.chmod(0o755)
    monkeypatch.setenv("WORKSPACE_ROOT", str(workspace_root))
    monkeypatch.setenv("SANDBOX_IMAGES", '["node:20-slim", "python:3.12-slim"]')
    git_config = tmp_path / "fixture-gitconfig"
    git_config.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(git_config))
    engine = get_engine(database_url)
    session_maker = get_session_factory(engine)
    redis_client = redis_async.from_url(redis_url)
    worker_log = tmp_path / "worker.log"
    process: subprocess.Popen[str] | None = None
    consumer_name = f"forge-e2e-{uuid4().hex}"

    try:
        async with redis_client:
            with worker_log.open("w") as output:
                process = subprocess.Popen(
                    [sys.executable, "-m", "apps.worker.main"],
                    cwd=Path(__file__).resolve().parents[2],
                    env={**os.environ, "HOSTNAME": consumer_name, "PYTHONUNBUFFERED": "1"},
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                await _wait_for_worker(redis_client, process, worker_log, consumer_name)

                for content, expected_verification, language in (
                    ("expected\n", VerificationStatus.PASSED, "javascript"),
                    ("wrong\n", VerificationStatus.FAILED, "javascript"),
                    ("expected\n", VerificationStatus.PASSED, "python"),
                    ("wrong\n", VerificationStatus.FAILED, "python"),
                ):
                    organization_id, user_id, repository_id, plan_id = (uuid4() for _ in range(4))
                    workspace = workspace_root / str(organization_id) / str(repository_id)
                    workspace.parent.mkdir(mode=0o755)
                    with git_config.open("a") as config:
                        config.write(f"[safe]\n\tdirectory = {workspace.as_posix()}\n")
                    base_sha = _fixture_repository(workspace, language)
                    edit_id, command_id = uuid4(), uuid4()
                    set_system_context()
                    async with session_maker() as session:
                        session.add_all(
                            [
                                OrganizationModel(id=organization_id, name=f"forge-e2e-{organization_id}"),
                                UserModel(id=user_id, email=f"{user_id}@example.invalid", name="Forge CI"),
                            ]
                        )
                        await session.flush()
                        session.add_all(
                            [
                                RoleBindingModel(id=uuid4(), organization_id=organization_id, user_id=user_id, role="OWNER"),
                                RepositoryModel(
                                    id=repository_id,
                                    organization_id=organization_id,
                                    owner="fixture",
                                    name=str(repository_id),
                                    full_name=f"fixture/{repository_id}",
                                    clone_url="https://example.invalid/fixture.git",
                                    status=RepositoryStatus.READY,
                                    commit_sha=base_sha,
                                    primary_language=language,
                                ),
                            ]
                        )
                        await session.flush()
                        session.add(
                            PlanModel(
                                id=plan_id,
                                organization_id=organization_id,
                                repository_id=repository_id,
                                status=PlanStatus.APPROVED,
                                intent="Test the worker",
                                context_snapshot={},
                            )
                        )
                        await session.flush()
                        session.add_all(
                            [
                                TaskNodeModel(
                                    id=edit_id,
                                    organization_id=organization_id,
                                    plan_id=plan_id,
                                    action_type="edit_file",
                                    target="result.txt",
                                    parameters={"changes": content},
                                ),
                                TaskNodeModel(
                                    id=command_id,
                                    organization_id=organization_id,
                                    plan_id=plan_id,
                                    action_type="command",
                                    target="workspace",
                                    parameters={"command": ("python3 -c 'import pathlib; assert pathlib.Path(\"result.txt\").is_file()'"
                                                            if language == "python" else "test -f result.txt")},
                                ),
                            ]
                        )
                        await session.flush()
                        session.add(
                            TaskEdgeModel(
                                id=uuid4(),
                                organization_id=organization_id,
                                plan_id=plan_id,
                                from_node_id=edit_id,
                                to_node_id=command_id,
                            )
                        )
                        await session.commit()

                    async with session_maker() as session:
                        authorized = await _verify_and_set_tenant(None, str(organization_id), {"id": user_id}, session, "plan:approve")
                        submitted = await start_execution(plan_id, StartExecutionRequest(), authorized, session)
                        job_id: UUID = submitted.id
                        event = (
                            await session.execute(
                                select(OutboxEventModel).where(
                                    OutboxEventModel.event_type == "execution.requested",
                                    OutboxEventModel.aggregate_id == str(job_id),
                                )
                            )
                        ).scalar_one()
                        event_id = str(event.id)

                    try:
                        async with asyncio.timeout(90):
                            while True:
                                if process.poll() is not None:
                                    pytest.fail(f"Worker exited during execution:\n{worker_log.read_text()[-4000:]}")
                                async with session_maker() as session:
                                    verification = (
                                        await session.execute(
                                            select(VerificationJobModel).where(
                                                VerificationJobModel.execution_job_id == job_id,
                                                VerificationJobModel.organization_id == organization_id,
                                            )
                                        )
                                    ).scalar_one_or_none()
                                    if verification and verification.status in {
                                        VerificationStatus.PASSED,
                                        VerificationStatus.FAILED,
                                        VerificationStatus.BLOCKED,
                                        VerificationStatus.NOT_CONFIGURED,
                                    }:
                                        break
                                await asyncio.sleep(0.2)
                    except TimeoutError:
                        pytest.fail(f"Worker did not finish job {job_id}:\n{worker_log.read_text()[-4000:]}")

                    async with session_maker() as session:
                        authorized = await _verify_and_set_tenant(None, str(organization_id), {"id": user_id}, session, "exec:read")
                        delivered_job = await get_execution_status(job_id, authorized, session)
                        delivered_mutations = await get_execution_mutations(job_id, authorized, session)
                        delivered_logs = await get_execution_logs(job_id, authorized, session)
                        delivered_verification = await get_latest_verification(job_id, authorized, session)
                        processed = (
                            await session.execute(
                                select(ProcessedEventModel).where(
                                    ProcessedEventModel.event_id == event_id,
                                    ProcessedEventModel.consumer_name == "forge_worker_group",
                                )
                            )
                        ).scalar_one_or_none()

                    assert delivered_job.status == ExecutionStatus.COMPLETED
                    assert delivered_mutations["mutations"][0]["file_path"] == "result.txt"
                    assert delivered_mutations["mutations"][0]["diff_hunk"]
                    assert any("Execution completed successfully" in entry.message for entry in delivered_logs)
                    assert delivered_verification["status"] == expected_verification
                    assert delivered_verification["results"][0].status == expected_verification
                    assert processed is not None
                    assert (workspace / "result.txt").read_text() == content
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, 5)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait, 5)
        try:
            _cleanup_owned_sandboxes(workspace_root)
        finally:
            try:
                await redis_client.aclose()
            finally:
                try:
                    await dispose_engine()
                finally:
                    if sys.platform != "win32":
                        shutil.rmtree(tmp_path)
