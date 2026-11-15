import asyncio
import json
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database.models.auth import OrganizationModel
from packages.database.models.execution import ExecutionEventModel, ExecutionJobModel, ExecutionStatus
from packages.database.models.planning import PlanModel, PlanStatus
from packages.database.models.repository import RepositoryModel, RepositoryStatus
from packages.database.tenant import set_system_context
from packages.shared.identifiers import OrganizationId
from services.execution.api import execution_timeline, export_execution_timeline, get_execution_event
from services.execution.flight_recorder import SAFE_KEYS, record_event


@pytest.mark.asyncio
async def test_flight_recorder_ordering_idempotency_rollback_and_tenant_scope():
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Disposable migrated PostgreSQL database required")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    org, repo, plan, job = (uuid4() for _ in range(4))
    set_system_context()
    try:
        async with sessions() as session:
            session.add(OrganizationModel(id=org, name=f"Flight Recorder {org}"))
            await session.flush()
            session.add(RepositoryModel(id=repo, organization_id=org, owner="fixture", name="flight",
                                        full_name="fixture/flight", clone_url="https://example.invalid/flight.git",
                                        status=RepositoryStatus.READY, commit_sha="a" * 40))
            await session.flush()
            session.add(PlanModel(id=plan, organization_id=org, repository_id=repo,
                                  status=PlanStatus.APPROVED, intent="Flight test", context_snapshot={}))
            await session.flush()
            session.add(ExecutionJobModel(id=job, organization_id=org, repository_id=repo, plan_id=plan,
                                          status=ExecutionStatus.PENDING, commit_sha_before="a" * 40))
            await session.commit()

        async def append(number: int):
            async with sessions() as session:
                event = await record_event(session, org, job, "execution.queued", "system", "test.flight",
                                           data={"retry_count": number}, idempotency_key=f"test-{number}")
                await session.commit()
                return event.id

        ids = await asyncio.gather(*(append(number) for number in range(8)))
        assert len(set(ids)) == 8
        assert await append(3) == ids[3]
        async with sessions() as session:
            await record_event(session, org, job, "execution.failed", "system", "test.flight",
                               data={"reason_code": "TEST_ROLLBACK"})
            await session.rollback()
        async with sessions() as session:
            page = await execution_timeline(job, 0, 3, None, None, None, OrganizationId(org), session)
            assert [event["sequence"] for event in page["events"]] == [1, 2, 3]
            assert page["next_cursor"] == 3
            second = await execution_timeline(job, 3, 10, None, None, None, OrganizationId(org), session)
            assert [event["sequence"] for event in second["events"]] == [4, 5, 6, 7, 8]
            assert second["next_cursor"] is None
            assert (await execution_timeline(job, 0, 20, "execution.queued", "system", 0, OrganizationId(org), session))["events"] == page["events"] + second["events"]
            assert (await get_execution_event(job, ids[0], OrganizationId(org), session))["id"] == str(ids[0])
            assert await session.scalar(select(ExecutionEventModel).where(
                ExecutionEventModel.execution_job_id == job,
                ExecutionEventModel.event_type == "execution.failed",
            )) is None
            with pytest.raises(ValueError, match="Unsafe"):
                await record_event(session, org, job, "execution.queued", "system", "test.flight",
                                   data={"password": "secret"})
            redacted = await record_event(session, org, job, "model.completed", "agent", "test.flight",
                                          data={"model": "sk-test-credential"})
            assert redacted.data["model"].startswith("sha256:")
            assert "sk-test-credential" not in json.dumps(redacted.data)
            await session.rollback()
            with pytest.raises(ValueError, match="exceeds limit"):
                await record_event(session, org, job, "execution.queued", "system", "test.flight",
                                   data={key: "a" * 128 for key in SAFE_KEYS})
            response = await export_execution_timeline(job, OrganizationId(org), session)
            exported = json.loads(b"".join([part.encode() if isinstance(part, str) else part async for part in response.body_iterator]))
            assert exported["execution_id"] == str(job)
            assert exported["schema_version"] == 1
            assert exported["events"] == page["events"] + second["events"]
            with pytest.raises(DBAPIError):
                await session.execute(text("UPDATE execution_events SET summary = 'tampered' WHERE execution_job_id = :id"), {"id": job})
            await session.rollback()
            with pytest.raises(DBAPIError):
                await session.execute(text("DELETE FROM execution_events WHERE execution_job_id = :id"), {"id": job})
            await session.rollback()
            with pytest.raises(HTTPException) as hidden:
                await get_execution_event(job, ids[0], OrganizationId(uuid4()), session)
            assert hidden.value.status_code == 404
        async with engine.begin() as connection:
            await connection.execute(text("""DO $$ BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'forge_flight_rls_test') THEN
                    CREATE ROLE forge_flight_rls_test NOLOGIN NOSUPERUSER NOBYPASSRLS;
                END IF;
            END $$"""))
            await connection.execute(text("GRANT USAGE ON SCHEMA public TO forge_flight_rls_test"))
            await connection.execute(text("GRANT SELECT ON execution_events TO forge_flight_rls_test"))
            await connection.execute(text("SET LOCAL ROLE forge_flight_rls_test"))
            query = text("SELECT id FROM execution_events WHERE execution_job_id = :job")
            await connection.execute(text("SELECT set_config('forge.organization_id', :org, true)"), {"org": str(uuid4())})
            assert (await connection.execute(query, {"job": job})).all() == []
            await connection.execute(text("SELECT set_config('forge.organization_id', :org, true)"), {"org": str(org)})
            assert len((await connection.execute(query, {"job": job})).all()) == 8
    finally:
        await engine.dispose()
