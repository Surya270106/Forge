"""Exercise import claims against an isolated, migrated PostgreSQL database."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database.models.auth import OrganizationModel
from packages.database.models.import_job import ImportJobModel, ImportJobStatus
from packages.database.models.repository import RepositoryModel, RepositoryStatus
from packages.database.tenant import set_system_context
from services.repository_import.worker import ImportWorker, claim_import_job
from packages.shared.config import ForgeSettings
from services.worker_recovery import fail_stale_jobs


@pytest.mark.asyncio
async def test_import_replay_concurrent_claim_and_genuine_failure(tmp_path):
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    if not url:
        if os.environ.get("CI") or os.environ.get("FORGE_REQUIRE_RLS_TEST"):
            pytest.fail("FORGE_RLS_TEST_DATABASE_URL is required")
        pytest.skip("Set FORGE_RLS_TEST_DATABASE_URL to an isolated migrated PostgreSQL database")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    organization_id, repository_id = uuid4(), uuid4()
    job_id, failure_job_id, interrupted_job_id, terminal_failed_id, terminal_cancelled_id = (uuid4() for _ in range(5))
    set_system_context()
    try:
        async with sessions() as session:
            session.add(OrganizationModel(id=organization_id, name=f"Import replay {organization_id}"))
            await session.flush()
            session.add(RepositoryModel(
                id=repository_id, organization_id=organization_id, owner="fixture", name=str(repository_id),
                full_name=f"fixture/{repository_id}", clone_url="https://github.com/fixture/repo.git",
                status=RepositoryStatus.READY,
            ))
            await session.flush()
            session.add_all([
                ImportJobModel(id=job_id, organization_id=organization_id, repository_id=repository_id,
                               status=ImportJobStatus.PENDING, branch="main"),
                ImportJobModel(id=failure_job_id, organization_id=organization_id, repository_id=repository_id,
                               status=ImportJobStatus.PENDING, branch="main"),
                ImportJobModel(id=interrupted_job_id, organization_id=organization_id, repository_id=repository_id,
                               status=ImportJobStatus.PENDING, branch="main"),
                ImportJobModel(id=terminal_failed_id, organization_id=organization_id, repository_id=repository_id,
                               status=ImportJobStatus.FAILED, branch="main"),
                ImportJobModel(id=terminal_cancelled_id, organization_id=organization_id, repository_id=repository_id,
                               status=ImportJobStatus.CANCELLED, branch="main"),
            ])
            await session.commit()

        async def claim():
            async with sessions() as session:
                return await claim_import_job(session, job_id)

        assert sorted(await asyncio.gather(claim(), claim())) == [False, True]
        async with sessions() as session:
            job = await session.get(ImportJobModel, job_id)
            assert job is not None
            assert job.status == ImportJobStatus.AUTHENTICATING
            job.status = ImportJobStatus.COMPLETED
            job.commit_sha = "a" * 40
            await session.commit()
        assert await claim() is False
        async with sessions() as session:
            job = await session.get(ImportJobModel, job_id)
            assert job is not None
            assert job.status == ImportJobStatus.COMPLETED
            assert job.commit_sha == "a" * 40
        for terminal_id in (terminal_failed_id, terminal_cancelled_id):
            async with sessions() as session:
                assert await claim_import_job(session, terminal_id) is False
                terminal = await session.get(ImportJobModel, terminal_id)
                assert terminal is not None
                assert terminal.status in {ImportJobStatus.FAILED, ImportJobStatus.CANCELLED}

        async with sessions() as session:
            await session.execute(update(ImportJobModel).where(ImportJobModel.id == interrupted_job_id).values(
                status=ImportJobStatus.CLONING, updated_at=datetime.now(UTC) - timedelta(hours=1)))
            await session.commit()
        async with sessions() as session:
            counts = await fail_stale_jobs(session, organization_id)
            assert counts["import"] == 1
            interrupted = await session.get(ImportJobModel, interrupted_job_id)
            assert interrupted is not None
            assert interrupted.status == ImportJobStatus.FAILED
        async with sessions() as session:
            assert await claim_import_job(session, interrupted_job_id) is False

        worker = ImportWorker.__new__(ImportWorker)
        worker.session_factory = sessions
        worker.settings = cast(ForgeSettings, type("TestSettings", (), {"workspace_root": str(tmp_path)})())
        # No requester is present: this is a genuine import failure, not a replay.
        await worker.process_job(failure_job_id)
        async with sessions() as session:
            failed = (await session.execute(select(ImportJobModel).where(ImportJobModel.id == failure_job_id))).scalar_one()
            assert failed.status == ImportJobStatus.FAILED
            assert failed.error_message
    finally:
        await engine.dispose()
