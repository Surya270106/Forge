from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock
from unittest.mock import patch as mock_patch
from uuid import uuid4

import pytest

from packages.database.models.execution import ExecutionStatus
from packages.database.models.planning import PlanStatus
from services.worker_recovery import fail_stale_jobs

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_requested", [False, True])
async def test_stale_execution_fails_without_replaying_sandbox_actions(cancel_requested: bool):
    organization_id = uuid4()
    job = SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        plan_id=uuid4(),
        status=ExecutionStatus.RUNNING,
        started_at=datetime.now(UTC) - timedelta(hours=1),
        finished_at=None,
        error_message=None,
        lease_generation=0,
        cancellation_requested_at=datetime.now(UTC) if cancel_requested else None,
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
    with mock_patch("services.worker_recovery.record_event", new=AsyncMock()) as event:
        counts = await fail_stale_jobs(cast("AsyncSession", session), organization_id)

    assert counts == {"execution": 1, "verification": 0, "import": 0, "repair": 0}
    assert job.status == ExecutionStatus.FAILED
    assert plan.status == PlanStatus.FAILED
    assert job.finished_at is not None
    session.commit.assert_awaited_once()
    assert event.await_count == 2
    assert event.await_args_list[-1].args[3] == (
        "execution.cancellation_failed" if cancel_requested else "execution.failed"
    )
