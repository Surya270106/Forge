import asyncio
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database.models.auth import OrganizationModel, UserModel
from packages.database.models.execution import ExecutionEventModel, ExecutionJobModel, ExecutionStatus
from packages.database.models.outbox_event import OutboxEventModel
from packages.database.models.planning import PlanModel, PlanStatus, TaskNodeModel
from packages.database.models.repository import RepositoryModel, RepositoryStatus
from packages.database.models.verification import (
    RepairAttemptModel,
    RepairAttemptStatus,
    VerificationJobModel,
    VerificationStatus,
)
from packages.database.tenant import set_system_context
from packages.shared.config import ForgeSettings
from services.execution.cancellation import request_execution_cancellation
from services.execution.sandbox import DockerSandbox, SandboxResult, SandboxRuntime
from services.execution.worker import ExecutionWorker
from services.execution.workspace import execution_workspace_path
from services.verification.service import VerificationDispatcher
from services.worker_recovery import fail_stale_jobs


@pytest.mark.asyncio
async def test_completed_execution_keeps_its_result_when_pending_verification_is_cancelled():
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Disposable migrated PostgreSQL database required")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    org, repo, plan, job, verification, actor, old_verification, repair_id = (uuid4() for _ in range(8))
    set_system_context()
    try:
        async with sessions() as session:
            session.add(OrganizationModel(id=org, name=f"Verification cancellation {org}"))
            session.add(UserModel(id=actor, email=f"verify-cancel-{actor}@example.invalid", name="Canceller"))
            await session.flush()
            session.add(RepositoryModel(id=repo, organization_id=org, owner="fixture", name="verify",
                                        full_name="fixture/verify", clone_url="https://example.invalid/verify.git",
                                        status=RepositoryStatus.READY, commit_sha="a" * 40))
            await session.flush()
            session.add(PlanModel(id=plan, organization_id=org, repository_id=repo, status=PlanStatus.COMPLETED,
                                  intent="Cancel verification", context_snapshot={}))
            await session.flush()
            session.add(ExecutionJobModel(id=job, organization_id=org, repository_id=repo, plan_id=plan,
                                          status=ExecutionStatus.COMPLETED, commit_sha_before="a" * 40))
            await session.flush()
            session.add(VerificationJobModel(id=verification, organization_id=org, repository_id=repo,
                                             execution_job_id=job, status=VerificationStatus.PENDING))
            session.add(VerificationJobModel(id=old_verification, organization_id=org, repository_id=repo,
                                             execution_job_id=job, status=VerificationStatus.FAILED))
            await session.flush()
            session.add(RepairAttemptModel(id=repair_id, organization_id=org, repository_id=repo,
                                           verification_job_id=old_verification, repair_execution_id=job,
                                           status=RepairAttemptStatus.REVERIFYING))
            await session.commit()
        async with sessions() as session:
            current = await request_execution_cancellation(session, org, job, actor)
            assert current.status == ExecutionStatus.COMPLETED
            assert current.cancellation_requested_at is not None
            check = await session.get(VerificationJobModel, verification)
            assert check is not None and check.status == VerificationStatus.CANCELLED
            repair = await session.get(RepairAttemptModel, repair_id)
            assert repair is not None and repair.status == RepairAttemptStatus.CANCELLED
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("real_docker", [False, True])
async def test_running_verifier_stops_after_completed_execution_cancellation(tmp_path: Path, monkeypatch, real_docker: bool):
    if real_docker and os.getenv("FORGE_REQUIRE_DOCKER_CANCEL") != "1":
        pytest.skip("Disposable Docker daemon access required")
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Disposable migrated PostgreSQL database required")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    org, repo, plan, job, verification, actor = (uuid4() for _ in range(6))
    workspace = execution_workspace_path(str(tmp_path), org, repo, job, 1)
    workspace.mkdir(parents=True)
    (workspace / "forge.yaml").write_text(
        '{"version":1,"languages":["node"],"verification":{"test":[{"identifier":"long",'
        '"display_name":"Long","category":"test","command":["sh","-c","sleep 60"]}]}}'
    )
    set_system_context()
    try:
        async with sessions() as session:
            session.add(OrganizationModel(id=org, name=f"Running verification cancellation {org}"))
            session.add(UserModel(id=actor, email=f"running-verify-{actor}@example.invalid", name="Canceller"))
            await session.flush()
            session.add(RepositoryModel(id=repo, organization_id=org, owner="fixture", name="verify-running",
                                        full_name="fixture/verify-running", clone_url="https://example.invalid/verify.git",
                                        status=RepositoryStatus.READY, commit_sha="a" * 40))
            await session.flush()
            session.add(PlanModel(id=plan, organization_id=org, repository_id=repo, status=PlanStatus.COMPLETED,
                                  intent="Cancel running verification", context_snapshot={}))
            await session.flush()
            session.add(ExecutionJobModel(id=job, organization_id=org, repository_id=repo, plan_id=plan,
                                          status=ExecutionStatus.COMPLETED, commit_sha_before="a" * 40,
                                          lease_generation=1))
            await session.flush()
            session.add(VerificationJobModel(id=verification, organization_id=org, repository_id=repo,
                                             execution_job_id=job, status=VerificationStatus.PENDING))
            await session.commit()
        entered, cleaned = asyncio.Event(), asyncio.Event()
        sandboxes: list[DockerSandbox] = []

        class WaitingSandbox:
            def __init__(self, *_args, **_kwargs):
                pass

            async def _ensure_container(self):
                pass

            async def run_command(self, *_args, **_kwargs):
                entered.set()
                await asyncio.Event().wait()

            async def cleanup(self):
                cleaned.set()

        class TrackingDockerSandbox(DockerSandbox):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                sandboxes.append(self)

            async def _ensure_container(self):
                await super()._ensure_container()
                entered.set()

            async def cleanup(self):
                await super().cleanup()
                cleaned.set()

        monkeypatch.setattr("services.verification.service.DockerSandbox",
                            TrackingDockerSandbox if real_docker else WaitingSandbox)
        settings = ForgeSettings(workspace_root=str(tmp_path), redis_url=os.environ.get("FORGE_TEST_REDIS_URL", "redis://localhost:6379/0"))

        async def run_verifier():
            async with sessions() as session:
                await VerificationDispatcher(session, org, settings, session_maker=sessions).run_verification(verification)

        running = asyncio.create_task(run_verifier())
        await asyncio.wait_for(entered.wait(), timeout=10)
        if real_docker:
            await asyncio.sleep(0.3)
        async with sessions() as session:
            current = await request_execution_cancellation(session, org, job, actor)
            assert current.status == ExecutionStatus.COMPLETED
            assert current.cancellation_requested_at is not None
        await asyncio.wait_for(running, timeout=5)
        assert cleaned.is_set()
        if real_docker:
            assert sandboxes and sandboxes[0].container_id is None
            assert subprocess.run(["docker", "inspect", sandboxes[0].container_name],
                                  capture_output=True, timeout=10).returncode != 0
        async with sessions() as session:
            current = await session.get(ExecutionJobModel, job)
            assert current is not None and current.status == ExecutionStatus.COMPLETED
            check = await session.get(VerificationJobModel, verification)
            assert check is not None and check.status == VerificationStatus.CANCELLED
            events = (await session.execute(select(ExecutionEventModel.event_type).where(
                ExecutionEventModel.execution_job_id == job))).scalars().all()
            assert "verification.cancellation_started" in events
            assert "verification.cancelled" in events
            assert "verification.completed" not in events
            if real_docker:
                assert "sandbox.cleanup_completed" in events
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_queued_and_running_cancellation_is_durable_and_idempotent():
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Disposable migrated PostgreSQL database required")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    org, repo, plan, queued, running, actor = (uuid4() for _ in range(6))
    set_system_context()
    try:
        async with sessions() as session:
            session.add(OrganizationModel(id=org, name=f"Cancellation {org}"))
            session.add(UserModel(id=actor, email=f"cancel-{actor}@example.invalid", name="Canceller"))
            await session.flush()
            session.add(RepositoryModel(id=repo, organization_id=org, owner="fixture", name="cancel",
                                        full_name="fixture/cancel", clone_url="https://example.invalid/cancel.git",
                                        status=RepositoryStatus.READY, commit_sha="a" * 40))
            await session.flush()
            session.add(PlanModel(id=plan, organization_id=org, repository_id=repo, status=PlanStatus.APPROVED,
                                  intent="Cancel test", context_snapshot={}))
            await session.flush()
            session.add_all([
                ExecutionJobModel(id=queued, organization_id=org, repository_id=repo, plan_id=plan,
                                  status=ExecutionStatus.PENDING, commit_sha_before="a" * 40),
                ExecutionJobModel(id=running, organization_id=org, repository_id=repo, plan_id=plan,
                                  status=ExecutionStatus.RUNNING, commit_sha_before="a" * 40),
            ])
            await session.commit()

        async with sessions() as session:
            queued_job = await request_execution_cancellation(session, org, queued, actor)
            running_job = await request_execution_cancellation(session, org, running, actor)
            assert queued_job.status == ExecutionStatus.CANCELLED
            assert queued_job.finished_at is not None
            current_plan = await session.get(PlanModel, plan)
            assert current_plan is not None and current_plan.status == PlanStatus.CANCELLED
            assert running_job.status == ExecutionStatus.RUNNING
            assert running_job.cancellation_requested_at is not None
            assert running_job.finished_at is None
            assert (await request_execution_cancellation(session, org, queued, actor)).status == ExecutionStatus.CANCELLED
            assert (await request_execution_cancellation(session, org, running, actor)).status == ExecutionStatus.RUNNING
            events = (await session.execute(select(ExecutionEventModel).where(
                ExecutionEventModel.execution_job_id.in_([queued, running])))).scalars().all()
            assert sorted(event.event_type for event in events) == [
                "execution.cancel_requested", "execution.cancel_requested", "execution.cancelled"
            ]
            outbox = (await session.execute(select(OutboxEventModel).where(
                OutboxEventModel.aggregate_id.in_([str(queued), str(running)]),
                OutboxEventModel.event_type == "execution.cancel_requested"))).scalars().all()
            assert len(outbox) == 2
            assert (await session.scalar(select(OutboxEventModel.id).where(
                OutboxEventModel.aggregate_id == str(queued),
                OutboxEventModel.event_type == "execution.cancelled"))) is not None
            with pytest.raises(HTTPException) as missing:
                await request_execution_cancellation(session, uuid4(), running, actor)
            assert missing.value.status_code == 404

        async with sessions() as session:
            current = await session.get(ExecutionJobModel, running)
            assert current is not None
            current.lease_owner = "interrupted-worker"
            current.lease_generation = 1
            current.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()
        async with sessions() as session:
            assert (await fail_stale_jobs(session, org))["execution"] == 1
            current = await session.get(ExecutionJobModel, running)
            assert current is not None
            assert current.status == ExecutionStatus.FAILED
            assert current.cancellation_requested_at is not None
            events = (await session.execute(select(ExecutionEventModel.event_type).where(
                ExecutionEventModel.execution_job_id == running))).scalars().all()
            assert "execution.cancellation_failed" in events
            assert "execution.recovered" not in events
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("real_docker", [False, True])
@pytest.mark.parametrize("redis_available", [True, False])
@pytest.mark.parametrize("abort_mode", ["cancel", "timeout", "error"])
async def test_running_worker_stops_command_and_finishes_cancellation(
    tmp_path: Path, real_docker: bool, redis_available: bool, abort_mode: str,
):
    if real_docker and abort_mode != "cancel":
        pytest.skip("Synthetic timeout/error is only for the fake sandbox")
    if real_docker and os.getenv("FORGE_REQUIRE_DOCKER_CANCEL") != "1":
        pytest.skip("Disposable Docker daemon access required")
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Disposable migrated PostgreSQL database required")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    org, repo, plan, job, actor = (uuid4() for _ in range(5))
    source = tmp_path / str(org) / str(repo)
    source.mkdir(parents=True)
    subprocess.run(["git", "-C", str(source), "init", "-b", "main"], check=True, capture_output=True)
    (source / "file.txt").write_text("base\n")
    subprocess.run(["git", "-C", str(source), "add", "file.txt"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=Forge Test", "-c", "user.email=test@example.invalid",
                    "commit", "-m", "base"], check=True, capture_output=True)
    base = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()
    set_system_context()
    try:
        async with sessions() as session:
            session.add(OrganizationModel(id=org, name=f"Worker cancellation {org}"))
            session.add(UserModel(id=actor, email=f"worker-cancel-{actor}@example.invalid", name="Canceller"))
            await session.flush()
            session.add(RepositoryModel(id=repo, organization_id=org, owner="fixture", name="stop",
                                        full_name="fixture/stop", clone_url="https://example.invalid/stop.git",
                                        status=RepositoryStatus.READY, commit_sha=base))
            await session.flush()
            session.add(PlanModel(id=plan, organization_id=org, repository_id=repo, status=PlanStatus.APPROVED,
                                  intent="Stop long command", context_snapshot={}))
            await session.flush()
            session.add(TaskNodeModel(id=uuid4(), organization_id=org, plan_id=plan,
                                      action_type="command", target="workspace", parameters={"command": "sleep 30"}))
            session.add(ExecutionJobModel(id=job, organization_id=org, repository_id=repo, plan_id=plan,
                                          status=ExecutionStatus.PENDING, commit_sha_before=base))
            await session.commit()

        entered, cleaned = asyncio.Event(), asyncio.Event()

        async def command(*_args, **_kwargs):
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                if abort_mode == "timeout":
                    raise TimeoutError from None
                if abort_mode == "error":
                    raise RuntimeError("Command aborted during cancellation") from None
                raise
            return SandboxResult(exit_code=0, stdout="", stderr="")

        async def cleanup():
            cleaned.set()

        sandbox = DockerSandbox(str(tmp_path), image="node:20-slim") if real_docker else cast("SandboxRuntime", SimpleNamespace(
            run_command=command, cleanup=cleanup,
        ))
        settings = ForgeSettings(workspace_root=str(tmp_path), redis_url=(
            os.environ.get("FORGE_TEST_REDIS_URL", "redis://localhost:6379/0") if redis_available else "redis://127.0.0.1:1/0"
        ))

        async def run_worker():
            async with sessions() as session:
                await ExecutionWorker(session, sandbox, settings=settings, session_maker=sessions).execute_job(job)

        worker = asyncio.create_task(run_worker())
        if real_docker:
            assert isinstance(sandbox, DockerSandbox)
            async with asyncio.timeout(15):
                while sandbox.container_id is None:
                    if worker.done():
                        await worker
                    await asyncio.sleep(0.1)
            await asyncio.sleep(0.3)
        else:
            await asyncio.wait_for(entered.wait(), timeout=10)
        async with sessions() as session:
            assert (await request_execution_cancellation(session, org, job, actor)).status == ExecutionStatus.RUNNING
        await asyncio.wait_for(worker, timeout=5)
        if real_docker:
            assert isinstance(sandbox, DockerSandbox)
            assert sandbox.container_id is None
            assert subprocess.run(["docker", "inspect", sandbox.container_name],
                                  capture_output=True, timeout=10).returncode != 0
        else:
            assert cleaned.is_set()
        async with sessions() as session:
            result = await session.get(ExecutionJobModel, job)
            assert result is not None and result.status == ExecutionStatus.CANCELLED
            current_plan = await session.get(PlanModel, plan)
            assert current_plan is not None and current_plan.status == PlanStatus.CANCELLED
            events = (await session.execute(select(ExecutionEventModel.event_type).where(
                ExecutionEventModel.execution_job_id == job))).scalars().all()
            assert "execution.cancellation_started" in events
            assert "execution.cancelled" in events
            assert "execution.completed" not in events
            assert (await session.scalar(select(OutboxEventModel.id).where(
                OutboxEventModel.aggregate_id == str(job),
                OutboxEventModel.event_type == "execution.cancelled"))) is not None
    finally:
        await engine.dispose()
