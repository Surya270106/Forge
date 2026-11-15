import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database.models.auth import OrganizationModel, UserModel
from packages.database.models.bench import BenchmarkRunModel, BenchmarkTrialModel
from packages.database.models.execution import ExecutionJobModel, ExecutionStatus
from packages.database.tenant import set_system_context
from services.bench.dataset import load_suite
from services.bench.service import cancel_run, create_run
from services.bench.worker import finish_trial, start_next_trial


@pytest.mark.asyncio
async def test_cancel_run_stops_pending_execution_and_remaining_trials(tmp_path):
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Disposable migrated PostgreSQL database required")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    org, owner = uuid4(), uuid4()
    set_system_context()
    try:
        async with sessions() as session:
            session.add_all([OrganizationModel(id=org, name=f"bench-cancel-{org}"),
                             UserModel(id=owner, name="Bench", email=f"bench-cancel-{owner}@example.invalid")])
            await session.commit()
        async with sessions() as session:
            run = await create_run(session, org, owner, suite_id=load_suite().id,
                                   task_ids=["clamp-boundary"], repetitions=2, idempotency_key=uuid4())
            run_id = run.id
        settings = SimpleNamespace(workspace_root=str(tmp_path))
        async with sessions() as session:
            await start_next_trial(session, org, run_id, settings)
            trials = (await session.execute(select(BenchmarkTrialModel).where(
                BenchmarkTrialModel.run_id == run_id))).scalars().all()
            execution_id = next(trial.execution_id for trial in trials if trial.execution_id)
            assert execution_id is not None
            await cancel_run(session, org, run_id, owner)
            await finish_trial(session, org, execution_id, settings)
            await start_next_trial(session, org, run_id, settings)
            cancelled_run = await session.get(BenchmarkRunModel, run_id)
            assert cancelled_run is not None and cancelled_run.status == "CANCELLED"
            assert {trial.status for trial in (await session.execute(select(BenchmarkTrialModel).where(
                BenchmarkTrialModel.run_id == run_id))).scalars().all()} == {"CANCELLED"}
            cancelled_execution = await session.get(ExecutionJobModel, execution_id)
            assert cancelled_execution is not None and cancelled_execution.status == ExecutionStatus.CANCELLED
    finally:
        await engine.dispose()
