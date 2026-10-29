from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from packages.database.models.verification import RepairAttemptModel, RepairAttemptStatus, VerificationJobModel, VerificationStatus
from services.verification.repair_worker import handle_repair_attempted

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_repair_event_prepares_reviewable_feedback_without_executing():
    organization_id, verification_job_id, repair_id = uuid4(), uuid4(), uuid4()
    repair = SimpleNamespace(
        organization_id=organization_id, verification_job_id=verification_job_id, status=RepairAttemptStatus.QUEUED, prompt_used=None
    )
    job = SimpleNamespace(organization_id=organization_id, status=VerificationStatus.FAILED)
    result = SimpleNamespace(verifier="pytest", exit_code=1, diagnostics=[{"message": "test failed"}], stderr="", stdout="")

    async def get(model, _id):
        return repair if model is RepairAttemptModel else job if model is VerificationJobModel else None

    session = SimpleNamespace(
        get=get, execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [result]))), commit=AsyncMock()
    )
    event = {"aggregate_id": str(repair_id), "organization_id": str(organization_id), "payload": {"verification_job_id": str(verification_job_id)}}

    await handle_repair_attempted(event, cast("AsyncSession", session))

    assert repair.status == RepairAttemptStatus.ELIGIBLE
    assert "test failed" in repair.prompt_used
    session.commit.assert_awaited_once()
