import asyncio
import os
import subprocess
from uuid import UUID, uuid4

import pytest
import redis.asyncio as redis_async
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database.models.auth import OrganizationModel, UserModel
from packages.database.models.bench import BenchmarkRunModel, BenchmarkTrialModel
from packages.database.models.execution import ExecutionJobModel
from packages.database.tenant import set_system_context
from packages.events.outbox import OutboxRelay
from packages.events.worker import EventWorker
from packages.shared.config import ForgeSettings
from services.bench.dataset import load_suite
from services.bench.service import create_run
from services.bench.worker import finish_trial, start_next_trial
from services.execution.sandbox import DockerSandbox
from services.execution.worker import ExecutionWorker


@pytest.mark.asyncio
async def test_bench_run_flows_through_outbox_redis_worker_and_grader():
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    redis_url = os.environ.get("REDIS_URL")
    workspace_root = os.environ.get("FORGE_BENCH_WORKSPACE_ROOT")
    if not url or not redis_url or not workspace_root or subprocess.run(
        ["docker", "info"], capture_output=True, timeout=10,
    ).returncode:
        pytest.skip("Disposable PostgreSQL, Redis, shared workspace, and Docker required")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    redis = redis_async.from_url(redis_url)
    settings = ForgeSettings(database_url=url, redis_url=redis_url, workspace_root=workspace_root)
    org, owner = uuid4(), uuid4()
    set_system_context()
    async with sessions() as session:
        session.add_all([OrganizationModel(id=org, name=f"bench-queue-{org}"),
                         UserModel(id=owner, name="Bench", email=f"bench-queue-{owner}@example.invalid")])
        await session.commit()
    async with sessions() as session:
        run = await create_run(session, org, owner, suite_id=load_suite().id,
                               task_ids=["clamp-boundary"], repetitions=1, idempotency_key=uuid4())
        run_id = run.id

    worker = EventWorker(redis, sessions, f"bench-test-{uuid4()}", "bench-test",
                         ["forge:events:bench", "forge:events:execution"])

    async def schedule(event_data, session):
        await start_next_trial(session, UUID(event_data["organization_id"]), UUID(event_data["aggregate_id"]), settings)

    async def execute(event_data, session):
        execution_id = UUID(event_data["aggregate_id"])
        job = await session.get(ExecutionJobModel, execution_id)
        assert job is not None
        sandbox = DockerSandbox(workspace_root, image="python:3.12-slim")
        try:
            await ExecutionWorker(session, sandbox, settings=settings, session_maker=sessions).execute_job(execution_id)
        finally:
            await sandbox.cleanup()

    async def finish(event_data, session):
        await finish_trial(session, UUID(event_data["organization_id"]), UUID(event_data["aggregate_id"]), settings)

    worker.register_handler("bench.run_requested", schedule)
    worker.register_handler("execution.requested", execute)
    for event in ("execution.completed", "execution.failed", "execution.cancelled"):
        worker.register_handler(event, finish)
    relay = OutboxRelay(sessions, redis, poll_interval=0.2)
    try:
        await worker.start()
        await relay.start()
        async with asyncio.timeout(40):
            while True:
                async with sessions() as session:
                    run = await session.get(BenchmarkRunModel, run_id)
                    trial = (await session.execute(select(BenchmarkTrialModel).where(
                        BenchmarkTrialModel.run_id == run_id))).scalar_one()
                    if run and run.status == "COMPLETED":
                        assert trial.status == "PASSED"
                        assert trial.result is not None and trial.result["passed"]
                        break
                await asyncio.sleep(0.2)
    finally:
        await relay.stop()
        await worker.stop()
        await redis.aclose()
        await engine.dispose()
