import asyncio
import os
import subprocess
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database.models.auth import OrganizationModel, UserModel
from packages.database.models.bench import BenchmarkTrialModel
from packages.database.models.execution import ExecutionEventModel, ExecutionJobModel, ExecutionStatus, MutationModel
from packages.database.models.planning import TaskEdgeModel, TaskNodeModel
from packages.database.tenant import set_system_context
from packages.shared.config import ForgeSettings
from services.bench.dataset import load_suite
from services.bench.service import create_run
from services.bench.worker import start_next_trial
from services.execution.sandbox import DockerSandbox
from services.execution.worker import ExecutionWorker
from services.execution.workspace import execution_workspace_path
from services.safety.service import revise_policy


@pytest.mark.parametrize("variant,denied,command,late,stop_running,protected_path", [
    ("correct", ["repository:write"], None, False, False, None),
    ("timeout", [], "echo safe; touch unauthorized.txt", False, False, None),
    ("correct", [], "echo safe; touch unauthorized.txt", True, False, None),
    ("timeout", [], "sleep 30", False, True, None),
    ("correct", [], None, False, False, ".env"),
], ids=["repository-denied", "command-denied", "late-command-denied", "emergency-stop", "sensitive-file"])
@pytest.mark.asyncio
async def test_safety_gate_blocks_real_worker_before_side_effect(variant, denied, command, late, stop_running,
                                                                 protected_path):
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    root = os.environ.get("FORGE_BENCH_WORKSPACE_ROOT")
    if not url or not root or subprocess.run(["docker", "info"], capture_output=True, timeout=10).returncode:
        pytest.skip("Disposable PostgreSQL, Docker socket, and shared workspace required")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    org, owner = uuid4(), uuid4()
    settings = ForgeSettings(workspace_root=root, database_url=url,
                             redis_url=os.environ.get("REDIS_URL", "redis://forge-bench-redis-1105:6379/0"))
    set_system_context()
    try:
        async with sessions() as session:
            session.add_all([OrganizationModel(id=org, name=f"safety-worker-{org}"),
                             UserModel(id=owner, name="Safety", email=f"safety-worker-{owner}@example.invalid")])
            await session.commit()
        async with sessions() as session:
            run = await create_run(session, org, owner, suite_id=load_suite().id,
                                   task_ids=["clamp-boundary"], repetitions=1, idempotency_key=uuid4(), variant=variant)
        async with sessions() as session:
            await start_next_trial(session, org, run.id, settings)
            trial = (await session.execute(select(BenchmarkTrialModel).where(
                BenchmarkTrialModel.run_id == run.id))).scalar_one()
            execution_id = trial.execution_id
            assert execution_id is not None
            if command or protected_path:
                node = (await session.execute(select(TaskNodeModel).where(TaskNodeModel.plan_id == trial.plan_id))).scalar_one()
                if protected_path:
                    node.target = protected_path
                elif late:
                    command_node = TaskNodeModel(id=uuid4(), organization_id=org, plan_id=trial.plan_id,
                                                 action_type="command", target="workspace", parameters={"command": command})
                    session.add(command_node)
                    await session.flush()
                    session.add(TaskEdgeModel(id=uuid4(), organization_id=org, plan_id=trial.plan_id,
                                              from_node_id=node.id, to_node_id=command_node.id))
                else:
                    node.parameters = {"command": command}
            await revise_policy(session, org, owner, denied=denied)
            await session.commit()
        sandbox = DockerSandbox(root, image="python:3.12-slim")
        try:
            async with sessions() as session:
                worker = ExecutionWorker(session, sandbox, settings=settings, session_maker=sessions)
                if stop_running:
                    running = asyncio.create_task(worker.execute_job(execution_id))
                    async with asyncio.timeout(20):
                        while sandbox.container_id is None:
                            if running.done():
                                await running
                                raise AssertionError("Command exited before emergency stop")
                            await asyncio.sleep(0.1)
                    async with sessions() as control:
                        await revise_policy(control, org, owner, stopped=True)
                        await control.commit()
                    await asyncio.wait_for(running, timeout=15)
                else:
                    await worker.execute_job(execution_id)
        finally:
            await sandbox.cleanup()
        async with sessions() as session:
            job = await session.get(ExecutionJobModel, execution_id)
            assert job is not None and job.status == (ExecutionStatus.CANCELLED if stop_running else ExecutionStatus.FAILED)
            assert await session.scalar(select(MutationModel.id).where(MutationModel.execution_job_id == execution_id)) is None
            if not stop_running:
                assert await session.scalar(select(ExecutionEventModel.id).where(
                    ExecutionEventModel.execution_job_id == execution_id,
                    ExecutionEventModel.event_type == "safety.permission_denied")) is not None
            assert sandbox.container_id is None
            assert not (execution_workspace_path(root, org, trial.id, execution_id, job.lease_generation)
                        / "unauthorized.txt").exists()
    finally:
        await engine.dispose()
