from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from packages.database.models.execution import ExecutionStatus
from packages.database.models.planning import PlanStatus
from services.worker_recovery import fail_stale_jobs

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_stale_execution_fails_without_replaying_sandbox_actions():
    organization_id = uuid4()
    job = SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        plan_id=uuid4(),
        status=ExecutionStatus.RUNNING,
        started_at=datetime.now(UTC) - timedelta(hours=1),
        finished_at=None,
        error_message=None,
    )
    plan = SimpleNamespace(organization_id=organization_id, status=PlanStatus.EXECUTING)
    results = [[job], [], [], [], []]

    async def execute(_statement):
        items = results.pop(0)
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: items),
            scalar_one_or_none=lambda: None,
        )

    session = SimpleNamespace(execute=execute, get=AsyncMock(return_value=plan), commit=AsyncMock())
    counts = await fail_stale_jobs(cast("AsyncSession", session), organization_id)

    assert counts == {"execution": 1, "verification": 0, "import": 0, "repair": 0}
    assert job.status == ExecutionStatus.FAILED
    assert plan.status == PlanStatus.FAILED
    assert job.finished_at is not None
    session.commit.assert_awaited_once()
