import asyncio
import os
import subprocess
import sys
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database.models.auth import OrganizationModel
from packages.database.models.execution import ExecutionEventModel, ExecutionJobModel, ExecutionStatus, MutationModel
from packages.database.models.patch import PatchModel
from packages.database.models.planning import PlanModel, PlanStatus, TaskEdgeModel, TaskNodeModel
from packages.database.models.repository import RepositoryModel, RepositoryStatus
from packages.database.models.verification import VerificationJobModel
from packages.database.tenant import set_system_context
from packages.shared.config import ForgeSettings
from services.execution.lease import claim_execution, renew_execution
from services.execution.sandbox import DockerSandbox, SandboxResult, SandboxRuntime
from services.execution.worker import ExecutionWorker
from services.execution.workspace import execution_workspace_path, prepare_execution_workspace
from services.patch.service import PatchService
from services.verification.service import VerificationDispatcher
from services.worker_recovery import fail_stale_jobs


@pytest.mark.asyncio
async def test_database_connection_loss_rolls_back_lease_transition():
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("FORGE_RLS_TEST_DATABASE_URL requires a disposable migrated PostgreSQL database")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    organization_id, repository_id, plan_id, job_id = (uuid4() for _ in range(4))
    set_system_context()
    try:
        async with sessions() as session:
            session.add(OrganizationModel(id=organization_id, name=f"Database outage fixture {organization_id}"))
            await session.flush()
            session.add(RepositoryModel(
                id=repository_id, organization_id=organization_id, owner="fixture", name="db-outage",
                full_name="fixture/db-outage", clone_url="https://example.invalid/db-outage.git",
                status=RepositoryStatus.READY, commit_sha="a" * 40,
            ))
            await session.flush()
            session.add(PlanModel(
                id=plan_id, organization_id=organization_id, repository_id=repository_id,
                status=PlanStatus.APPROVED, intent="Database outage fixture", context_snapshot={},
            ))
            await session.flush()
            session.add(ExecutionJobModel(
                id=job_id, organization_id=organization_id, repository_id=repository_id,
                plan_id=plan_id, status=ExecutionStatus.PENDING, commit_sha_before="a" * 40,
            ))
            await session.commit()

        async with sessions() as interrupted:
            assert await claim_execution(interrupted, job_id, organization_id, str(uuid4()), 180, commit=False) == 1
            backend_pid = await interrupted.scalar(text("SELECT pg_backend_pid()"))
            async with sessions() as admin:
                assert await admin.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": backend_pid})
                await admin.commit()
            with pytest.raises(DBAPIError):
                await interrupted.commit()
        async with sessions() as session:
            job = await session.get(ExecutionJobModel, job_id)
            assert job is not None and job.status == ExecutionStatus.PENDING and job.lease_generation == 0
            assert await claim_execution(session, job_id, organization_id, str(uuid4()), 180) == 1
    finally:
        await engine.dispose()


@pytest.mark.parametrize("phase", ["after_claim", "after_sandbox_before_persist"])
@pytest.mark.asyncio
async def test_killed_lease_owner_is_recovered_with_new_generation(phase):
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("FORGE_RLS_TEST_DATABASE_URL requires a disposable migrated PostgreSQL database")
    if phase == "after_sandbox_before_persist" and subprocess.run(
        ["docker", "info"], capture_output=True, timeout=10, check=False,
    ).returncode != 0:
        pytest.skip("Docker daemon is required for the post-sandbox process kill")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    organization_id, repository_id, plan_id, job_id = (uuid4() for _ in range(4))
    owner = str(uuid4())
    child = None
    set_system_context()
    try:
        async with sessions() as session:
            session.add(OrganizationModel(id=organization_id, name=f"Killed lease fixture {organization_id}"))
            await session.flush()
            session.add(RepositoryModel(
                id=repository_id, organization_id=organization_id, owner="fixture", name="killed-lease",
                full_name="fixture/killed-lease", clone_url="https://example.invalid/killed-lease.git",
                status=RepositoryStatus.READY, commit_sha="a" * 40,
            ))
            await session.flush()
            session.add(PlanModel(
                id=plan_id, organization_id=organization_id, repository_id=repository_id,
                status=PlanStatus.APPROVED, intent="Killed lease fixture", context_snapshot={},
            ))
            await session.flush()
            session.add(ExecutionJobModel(
                id=job_id, organization_id=organization_id, repository_id=repository_id,
                plan_id=plan_id, status=ExecutionStatus.PENDING, commit_sha_before="a" * 40,
            ))
            await session.commit()

        script = """
import asyncio, os, sys
from uuid import UUID
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from packages.database.tenant import set_system_context
from services.execution.lease import claim_execution
from services.execution.sandbox import DockerSandbox
async def main():
    set_system_context()
    engine = create_async_engine(os.environ['FORGE_RLS_TEST_DATABASE_URL'])
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        generation = await claim_execution(session, UUID(sys.argv[1]), UUID(sys.argv[2]), sys.argv[3], 180)
    if sys.argv[4] == 'after_sandbox_before_persist':
        sandbox = DockerSandbox(os.getcwd(), image='alpine:latest')
        try:
            assert (await sandbox.run_command(['sh', '-c', 'true'])).exit_code == 0
        finally:
            await sandbox.cleanup()
    print(generation, flush=True)
    await asyncio.Event().wait()
asyncio.run(main())
"""
        child = subprocess.Popen(
            [sys.executable, "-u", "-c", script, str(job_id), str(organization_id), owner, phase],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        assert child.stdout is not None
        async with asyncio.timeout(15):
            while (claimed := await asyncio.to_thread(child.stdout.readline)) != "1\n":
                assert claimed, child.stderr.read() if child.poll() is not None and child.stderr else "Child exited"
        child.kill()
        assert await asyncio.to_thread(child.wait, 10) != 0

        async with sessions() as session:
            await session.execute(update(ExecutionJobModel).where(ExecutionJobModel.id == job_id).values(
                lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
            ))
            await session.commit()
            assert (await fail_stale_jobs(session, organization_id))["execution"] == 1
            history = (await session.execute(select(ExecutionEventModel.event_type).where(
                ExecutionEventModel.execution_job_id == job_id,
            ).order_by(ExecutionEventModel.sequence))).scalars().all()
            assert history == ["worker.lease_expired", "execution.recovered"]
        async with sessions() as session:
            assert await claim_execution(session, job_id, organization_id, str(uuid4()), 180) == 2
    finally:
        if child is not None and child.poll() is None:
            child.kill()
            await asyncio.to_thread(child.wait, 10)
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_claim_heartbeat_expiry_and_recovery():
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("FORGE_RLS_TEST_DATABASE_URL requires a disposable migrated PostgreSQL database")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    organization_id, repository_id, plan_id, job_id, node_id = (uuid4() for _ in range(5))
    owners = [str(uuid4()), str(uuid4())]
    set_system_context()
    try:
        async with sessions() as session:
            session.add(OrganizationModel(id=organization_id, name=f"Lease fixture {organization_id}"))
            await session.flush()
            session.add(RepositoryModel(
                id=repository_id, organization_id=organization_id, owner="fixture", name="lease",
                full_name="fixture/lease", clone_url="https://github.com/fixture/lease.git",
                status=RepositoryStatus.READY, commit_sha="a" * 40,
            ))
            await session.flush()
            session.add(PlanModel(
                id=plan_id, organization_id=organization_id, repository_id=repository_id,
                status=PlanStatus.APPROVED, intent="Lease fixture", context_snapshot={},
            ))
            await session.flush()
            session.add(TaskNodeModel(
                id=node_id, organization_id=organization_id, plan_id=plan_id,
                action_type="edit_file", target="file.txt", parameters={},
            ))
            session.add(ExecutionJobModel(
                id=job_id, organization_id=organization_id, repository_id=repository_id,
                plan_id=plan_id, status=ExecutionStatus.PENDING, commit_sha_before="a" * 40,
            ))
            await session.commit()

        async def claim(owner):
            async with sessions() as session:
                return await claim_execution(session, job_id, organization_id, owner, lease_seconds=30)

        claims = await asyncio.gather(*(claim(owner) for owner in owners))
        assert sum(generation is not None for generation in claims) == 1
        winner = claims.index(next(generation for generation in claims if generation is not None))
        generation = claims[winner]
        assert generation == 1
        async with sessions() as session:
            session.add(MutationModel(
                id=uuid4(), organization_id=organization_id, repository_id=repository_id,
                execution_job_id=job_id, task_node_id=node_id, file_path="file.txt",
                mutation_type="UPDATE", diff_hunk="partial attempt", is_reverted=False,
            ))
            await session.commit()
            assert await renew_execution(session, job_id, organization_id, owners[winner], generation, 30)
            assert not await renew_execution(session, job_id, organization_id, owners[1 - winner], generation, 30)
            await session.execute(update(ExecutionJobModel).where(ExecutionJobModel.id == job_id).values(
                lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
            ))
            await session.commit()
            assert not await renew_execution(session, job_id, organization_id, owners[winner], generation, 30)
            counts = await fail_stale_jobs(session, organization_id)
            assert counts["execution"] == 1
            job = await session.get(ExecutionJobModel, job_id)
            assert job is not None
            assert job.status == ExecutionStatus.PENDING
            assert job.lease_owner is None
            mutation = (await session.execute(select(MutationModel).where(
                MutationModel.execution_job_id == job_id
            ))).scalar_one()
            assert mutation.is_reverted
        assert await claim(owners[1 - winner]) == 2
        async with sessions() as session:
            assert not await renew_execution(session, job_id, organization_id, owners[winner], generation, 30)
            await session.execute(update(ExecutionJobModel).where(ExecutionJobModel.id == job_id).values(
                status=ExecutionStatus.CANCELLED,
                lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
            ))
            await session.commit()
            assert (await fail_stale_jobs(session, organization_id))["execution"] == 0
            cancelled_job = await session.get(ExecutionJobModel, job_id)
            assert cancelled_job is not None and cancelled_job.status == ExecutionStatus.CANCELLED
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_verification_requests_create_one_job():
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("FORGE_RLS_TEST_DATABASE_URL requires a disposable migrated PostgreSQL database")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    organization_id, repository_id, plan_id, job_id = (uuid4() for _ in range(4))
    set_system_context()
    try:
        async with sessions() as session:
            session.add(OrganizationModel(id=organization_id, name=f"Verification race fixture {organization_id}"))
            await session.flush()
            session.add(RepositoryModel(
                id=repository_id, organization_id=organization_id, owner="fixture", name="verify",
                full_name="fixture/verify", clone_url="https://github.com/fixture/verify.git",
                status=RepositoryStatus.READY, commit_sha="a" * 40,
            ))
            await session.flush()
            session.add(PlanModel(
                id=plan_id, organization_id=organization_id, repository_id=repository_id,
                status=PlanStatus.COMPLETED, intent="Verify once", context_snapshot={},
            ))
            await session.flush()
            session.add(ExecutionJobModel(
                id=job_id, organization_id=organization_id, repository_id=repository_id,
                plan_id=plan_id, status=ExecutionStatus.COMPLETED, commit_sha_before="a" * 40,
            ))
            await session.commit()

        async def trigger():
            async with sessions() as session:
                return (await VerificationDispatcher(session, organization_id).trigger_verification(job_id)).id

        first, second = await asyncio.gather(trigger(), trigger())
        async with sessions() as session:
            jobs = (await session.execute(select(VerificationJobModel).where(
                VerificationJobModel.execution_job_id == job_id
            ))).scalars().all()
        assert first == second
        assert len(jobs) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_patch_generation_returns_one_review_digest(monkeypatch):
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("FORGE_RLS_TEST_DATABASE_URL requires a disposable migrated PostgreSQL database")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    organization_id, repository_id, plan_id, job_id, node_id = (uuid4() for _ in range(5))
    set_system_context()
    try:
        async with sessions() as session:
            session.add(OrganizationModel(id=organization_id, name=f"Patch race fixture {organization_id}"))
            await session.flush()
            session.add(RepositoryModel(
                id=repository_id, organization_id=organization_id, owner="fixture", name="patch",
                full_name="fixture/patch", clone_url="https://github.com/fixture/patch.git",
                status=RepositoryStatus.READY, commit_sha="a" * 40,
            ))
            await session.flush()
            session.add(PlanModel(id=plan_id, organization_id=organization_id, repository_id=repository_id,
                                  status=PlanStatus.COMPLETED, intent="Patch once", context_snapshot={}))
            await session.flush()
            session.add(TaskNodeModel(id=node_id, organization_id=organization_id, plan_id=plan_id,
                                      action_type="edit_file", target="file.txt", parameters={}))
            session.add(ExecutionJobModel(id=job_id, organization_id=organization_id, repository_id=repository_id,
                                          plan_id=plan_id, status=ExecutionStatus.COMPLETED, commit_sha_before="a" * 40))
            await session.flush()
            session.add(MutationModel(
                id=uuid4(), organization_id=organization_id, repository_id=repository_id,
                execution_job_id=job_id, task_node_id=node_id, file_path="file.txt", mutation_type="UPDATE",
                diff_hunk="--- file.txt\n+++ file.txt\n@@ -1 +1 @@\n-old\n+new\n", is_reverted=False,
            ))
            await session.commit()

        original_mutations = PatchService._mutations_for_execution

        async def slow_mutations(service, execution_job_id):
            await asyncio.sleep(0.2)
            return await original_mutations(service, execution_job_id)

        monkeypatch.setattr(PatchService, "_mutations_for_execution", slow_mutations)

        async def generate():
            async with sessions() as session:
                patch = await PatchService(session, organization_id).generate_patch(job_id)
                return patch.id, patch.review_digest

        first, second = await asyncio.gather(generate(), generate())
        async with sessions() as session:
            patches = (await session.execute(select(PatchModel).where(
                PatchModel.execution_job_id == job_id
            ))).scalars().all()
        assert first == second
        assert len(patches) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_superseded_worker_cannot_persist_result_or_share_attempt_workspace(tmp_path: Path, monkeypatch):
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    redis_url = os.environ.get("FORGE_TEST_REDIS_URL")
    if not url or not redis_url:
        pytest.skip("Disposable PostgreSQL and Redis are required")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    organization_id, repository_id, plan_id, job_id, edit_id, command_id = (uuid4() for _ in range(6))
    source = tmp_path / str(organization_id) / str(repository_id)
    source.mkdir(parents=True)

    def git(*args):
        return subprocess.run(["git", "-C", str(source), *args], check=True,
                              capture_output=True, text=True, timeout=10).stdout.strip()

    git("init", "-b", "main")
    (source / "file.txt").write_text("base\n")
    git("add", "file.txt")
    git("-c", "user.name=Forge Test", "-c", "user.email=test@example.invalid", "commit", "-m", "base")
    base_sha = git("rev-parse", "HEAD")
    set_system_context()
    try:
        async with sessions() as session:
            session.add(OrganizationModel(id=organization_id, name=f"Fence fixture {organization_id}"))
            await session.flush()
            session.add(RepositoryModel(id=repository_id, organization_id=organization_id,
                                        owner="fixture", name="fence", full_name="fixture/fence",
                                        clone_url="https://github.com/fixture/fence.git", status=RepositoryStatus.READY,
                                        commit_sha=base_sha))
            await session.flush()
            session.add(PlanModel(id=plan_id, organization_id=organization_id, repository_id=repository_id,
                                  status=PlanStatus.APPROVED, intent="Fence fixture", context_snapshot={}))
            await session.flush()
            session.add_all([
                TaskNodeModel(id=edit_id, organization_id=organization_id, plan_id=plan_id,
                              action_type="edit_file", target="file.txt", parameters={"changes": "old worker\n"}),
                TaskNodeModel(id=command_id, organization_id=organization_id, plan_id=plan_id,
                              action_type="command", target="workspace", parameters={"command": "true"}),
            ])
            await session.flush()
            session.add(TaskEdgeModel(id=uuid4(), organization_id=organization_id, plan_id=plan_id,
                                      from_node_id=edit_id, to_node_id=command_id))
            session.add(ExecutionJobModel(id=job_id, organization_id=organization_id, repository_id=repository_id,
                                          plan_id=plan_id, status=ExecutionStatus.PENDING, commit_sha_before=base_sha))
            await session.commit()

        entered, release = asyncio.Event(), asyncio.Event()

        async def run_command(*_args, **_kwargs):
            entered.set()
            await release.wait()
            return SandboxResult(exit_code=0, stdout="", stderr="")

        sandbox = cast("SandboxRuntime", SimpleNamespace(run_command=run_command))
        settings = ForgeSettings(workspace_root=str(tmp_path), redis_url=redis_url)
        prepare_started, prepare_released, prepare_finished = threading.Event(), threading.Event(), threading.Event()
        original_prepare = prepare_execution_workspace

        def delayed_prepare(*args):
            prepare_started.set()
            prepare_released.wait(2)
            try:
                return original_prepare(*args)
            finally:
                prepare_finished.set()

        monkeypatch.setattr("services.execution.worker.prepare_execution_workspace", delayed_prepare)

        async def run_worker():
            async with sessions() as session:
                await ExecutionWorker(session, sandbox, settings=settings, session_maker=sessions).execute_job(job_id)

        task = asyncio.create_task(run_worker())
        assert await asyncio.wait_for(asyncio.to_thread(prepare_started.wait), timeout=5)
        assert not prepare_finished.is_set()
        prepare_released.set()
        await asyncio.wait_for(entered.wait(), timeout=10)
        monkeypatch.setattr("services.execution.worker.prepare_execution_workspace", original_prepare)
        async with sessions() as session:
            await asyncio.wait_for(session.execute(update(ExecutionJobModel).where(ExecutionJobModel.id == job_id).values(
                lease_owner="replacement", lease_generation=2,
                lease_expires_at=datetime.now(UTC) + timedelta(minutes=3),
            )), timeout=10)
            await session.commit()
        release.set()
        await asyncio.wait_for(task, timeout=10)
        async with sessions() as session:
            job = await session.get(ExecutionJobModel, job_id)
            mutations = (await session.execute(select(MutationModel).where(
                MutationModel.execution_job_id == job_id
            ))).scalars().all()
            assert job is not None
            assert job.status == ExecutionStatus.RUNNING
            assert job.lease_owner == "replacement"
            assert mutations == []
        old_workspace = execution_workspace_path(str(tmp_path), organization_id, repository_id, job_id, 1)
        replacement_workspace = prepare_execution_workspace(
            str(tmp_path), organization_id, repository_id, job_id, base_sha, 2
        )
        assert (old_workspace / "file.txt").read_text() == "old worker\n"
        assert (replacement_workspace / "file.txt").read_text() == "base\n"
        assert (source / "file.txt").read_text() == "base\n"

        async with sessions() as session:
            await session.execute(update(ExecutionJobModel).where(ExecutionJobModel.id == job_id).values(
                status=ExecutionStatus.PENDING, lease_owner=None, lease_expires_at=None,
            ))
            await session.commit()
        retry_workspace = execution_workspace_path(str(tmp_path), organization_id, repository_id, job_id, 3)
        retry_sandbox = DockerSandbox(workspace_root=str(old_workspace))

        async def retry_command(*_args, **_kwargs):
            assert retry_sandbox.workspace_root == str(retry_workspace)
            return SandboxResult(exit_code=0, stdout="", stderr="")

        monkeypatch.setattr(retry_sandbox, "run_command", retry_command)
        async with sessions() as session:
            await ExecutionWorker(session, retry_sandbox, settings=settings, session_maker=sessions).execute_job(job_id)
        async with sessions() as session:
            job = await session.get(ExecutionJobModel, job_id)
            assert job is not None and job.status == ExecutionStatus.COMPLETED
            assert job.lease_generation == 3
        assert (retry_workspace / "file.txt").read_text() == "old worker\n"
        assert (replacement_workspace / "file.txt").read_text() == "base\n"
    finally:
        await engine.dispose()
