import os
import subprocess
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database.models.auth import OrganizationModel, UserModel
from packages.database.models.bench import BenchmarkTrialModel
from packages.database.models.execution import ExecutionEventModel, ExecutionJobModel, ExecutionStatus
from packages.database.tenant import set_system_context
from packages.shared.config import ForgeSettings
from services.bench.dataset import load_suite
from services.bench.service import create_run
from services.bench.worker import finish_trial, start_next_trial
from services.execution.sandbox import DockerSandbox
from services.execution.worker import ExecutionWorker


@pytest.mark.parametrize("variant,expected", [("correct", "PASSED"), ("incorrect", "FAILED"),
                                               ("regression", "FAILED"), ("timeout", "FAILED")])
@pytest.mark.asyncio
async def test_benchmark_uses_real_worker_and_independent_docker_grader(variant, expected):
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    workspace_root = os.environ.get("FORGE_BENCH_WORKSPACE_ROOT")
    if not url or not workspace_root or subprocess.run(["docker", "info"], capture_output=True, timeout=10).returncode:
        pytest.skip("Disposable PostgreSQL, shared Docker workspace, and Docker socket required")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    org, owner = uuid4(), uuid4()
    task = load_suite().tasks[0]
    settings = ForgeSettings(workspace_root=workspace_root,
                             redis_url=os.environ.get("REDIS_URL", "redis://forge-bench-redis-1105:6379/0"),
                             database_url=url, execution_timeout_seconds=30)
    set_system_context()
    try:
        async with sessions() as session:
            session.add_all([OrganizationModel(id=org, name=f"bench-e2e-{org}"),
                             UserModel(id=owner, name="Bench", email=f"bench-e2e-{owner}@example.invalid")])
            await session.commit()
        async with sessions() as session:
            run = await create_run(session, org, owner, suite_id=load_suite().id,
                                   task_ids=[task.id], repetitions=1, idempotency_key=uuid4(), variant=variant)
            run_id = run.id
        async with sessions() as session:
            await start_next_trial(session, org, run_id, settings)
            trial = (await session.execute(select(BenchmarkTrialModel).where(
                BenchmarkTrialModel.run_id == run_id))).scalar_one()
            execution_id = trial.execution_id
        assert execution_id is not None
        sandbox = DockerSandbox(workspace_root, image="python:3.12-slim")
        try:
            async with sessions() as session:
                await ExecutionWorker(session, sandbox, settings=settings, session_maker=sessions).execute_job(execution_id)
        finally:
            await sandbox.cleanup()
        async with sessions() as session:
            await finish_trial(session, org, execution_id, settings)
            await finish_trial(session, org, execution_id, settings)  # Duplicate completion delivery.
            await start_next_trial(session, org, run_id, settings)
            trial = (await session.execute(select(BenchmarkTrialModel).where(
                BenchmarkTrialModel.run_id == run_id))).scalar_one()
            execution = await session.get(ExecutionJobModel, execution_id)
            assert trial.status == expected
            assert execution is not None
            if variant == "timeout":
                assert execution.status == ExecutionStatus.FAILED
                assert trial.result is None
            else:
                assert execution.status == ExecutionStatus.COMPLETED
                assert trial.result is not None
                assert trial.result["passed"] == (variant == "correct")
                assert trial.patch_digest == trial.result["patch_digest"]
                categories = {check["category"] for check in trial.result["checks"] if check["status"] == "failed"}
                if variant == "incorrect":
                    assert "correctness" in categories
                if variant == "regression":
                    assert "regression" in categories
            assert await session.scalar(select(ExecutionEventModel.id).where(
                ExecutionEventModel.execution_job_id == execution_id,
                ExecutionEventModel.event_type == ("bench.trial_scored" if trial.result else "bench.trial_failed"),
            )) is not None
    finally:
        await engine.dispose()
