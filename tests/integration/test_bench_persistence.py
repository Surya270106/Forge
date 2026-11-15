import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database.models.auth import OrganizationModel, UserModel
from packages.database.models.bench import BenchmarkRunModel, BenchmarkTrialModel
from packages.database.models.execution import ExecutionJobModel
from packages.database.tenant import set_system_context
from services.bench.api import _visible_run
from services.bench.dataset import load_suite
from services.bench.service import create_run
from services.bench.worker import start_next_trial


@pytest.mark.asyncio
async def test_run_idempotency_worker_scheduling_tenant_scope_and_result_immutability(tmp_path):
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Disposable migrated PostgreSQL database required")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    org_a, org_b, owner = uuid4(), uuid4(), uuid4()
    suite = load_suite()
    set_system_context()
    try:
        async with sessions() as session:
            session.add_all([OrganizationModel(id=org_a, name=f"bench-{org_a}"),
                             OrganizationModel(id=org_b, name=f"bench-{org_b}"),
                             UserModel(id=owner, name="Bench", email=f"bench-{owner}@example.invalid")])
            await session.commit()

        key = uuid4()
        async with sessions() as session:
            run = await create_run(session, org_a, owner, suite_id=suite.id,
                                   task_ids=[suite.tasks[0].id], repetitions=1, idempotency_key=key)
            first_id = run.id
        async with sessions() as session:
            duplicate = await create_run(session, org_a, owner, suite_id=suite.id,
                                         task_ids=[suite.tasks[0].id], repetitions=1, idempotency_key=key)
            assert duplicate.id == first_id
            with pytest.raises(HTTPException) as conflict:
                await create_run(session, org_a, owner, suite_id=suite.id,
                                 task_ids=[suite.tasks[1].id], repetitions=1, idempotency_key=key)
            assert conflict.value.status_code == 409
            with pytest.raises(HTTPException) as hidden:
                await _visible_run(session, org_b, first_id)
            assert hidden.value.status_code == 404

        settings = SimpleNamespace(workspace_root=str(tmp_path))
        async with sessions() as session:
            await start_next_trial(session, org_a, first_id, settings)
            await start_next_trial(session, org_a, first_id, settings)
            trial = (await session.execute(select(BenchmarkTrialModel).where(
                BenchmarkTrialModel.run_id == first_id))).scalar_one()
            assert trial.execution_id is not None and trial.status == "RUNNING"
            assert await session.scalar(select(ExecutionJobModel.id).where(
                ExecutionJobModel.id == trial.execution_id)) == trial.execution_id
            assert (tmp_path / str(org_a) / str(trial.id) / "forgebench.py").exists()
            trial.result = {"score": 100}
            trial.patch_digest = "a" * 64
            await session.commit()
            trial.result = {"score": 0}
            with pytest.raises(DBAPIError):
                await session.commit()
            await session.rollback()
            run = await session.get(BenchmarkRunModel, first_id)
            assert run is not None
            run.manifest = {"changed": True}
            with pytest.raises(DBAPIError):
                await session.commit()
            await session.rollback()

        async with engine.begin() as connection:
            await connection.execute(text("""DO $$ BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'forge_bench_rls_test') THEN
                    CREATE ROLE forge_bench_rls_test NOLOGIN NOSUPERUSER NOBYPASSRLS;
                END IF;
            END $$"""))
            await connection.execute(text("GRANT USAGE ON SCHEMA public TO forge_bench_rls_test"))
            await connection.execute(text("GRANT SELECT ON benchmark_runs, benchmark_trials TO forge_bench_rls_test"))
            await connection.execute(text("SET LOCAL ROLE forge_bench_rls_test"))
            await connection.execute(text("SELECT set_config('forge.organization_id', :org, true)"), {"org": str(org_b)})
            assert (await connection.execute(text("SELECT id FROM benchmark_runs WHERE id = :id"), {"id": first_id})).all() == []
            await connection.execute(text("SELECT set_config('forge.organization_id', :org, true)"), {"org": str(org_a)})
            assert len((await connection.execute(text("SELECT id FROM benchmark_runs WHERE id = :id"), {"id": first_id})).all()) == 1
    finally:
        await engine.dispose()
