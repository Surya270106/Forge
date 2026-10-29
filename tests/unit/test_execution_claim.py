from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from packages.database.models.execution import ExecutionStatus
from packages.database.models.planning import PlanStatus
from services.execution.worker import ExecutionWorker

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from services.execution.events import ExecutionEventPublisher
    from services.execution.sandbox import SandboxRuntime


@pytest.mark.asyncio
async def test_worker_rejects_job_whose_plan_is_no_longer_approved():
    organization_id, job_id = uuid4(), uuid4()
    job = SimpleNamespace(
        id=job_id,
        organization_id=organization_id,
        repository_id=uuid4(),
        plan_id=uuid4(),
        status=ExecutionStatus.PENDING,
        error_message=None,
        finished_at=None,
    )
    plan = SimpleNamespace(organization_id=organization_id, status=PlanStatus.REJECTED)
    repo = SimpleNamespace(organization_id=organization_id)
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: job)),
        get=AsyncMock(side_effect=[plan, repo]),
        commit=AsyncMock(),
    )
    sandbox = SimpleNamespace(run_command=AsyncMock())
    worker = ExecutionWorker(cast("AsyncSession", session), cast("SandboxRuntime", sandbox))
    publisher = SimpleNamespace(publish=AsyncMock())
    worker.publisher = cast("ExecutionEventPublisher", publisher)

    await worker.execute_job(job_id)

    assert job.status == ExecutionStatus.FAILED
    assert "Approved plan" in job.error_message
    sandbox.run_command.assert_not_awaited()
    publisher.publish.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_duplicate_event_does_not_execute_running_job():
    job = SimpleNamespace(status=ExecutionStatus.RUNNING)
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: job)), get=AsyncMock())
    sandbox = SimpleNamespace(run_command=AsyncMock())
    worker = ExecutionWorker(cast("AsyncSession", session), cast("SandboxRuntime", sandbox))

    await worker.execute_job(uuid4())

    session.get.assert_not_awaited()
    sandbox.run_command.assert_not_awaited()
