from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from packages.database.models.memory import IndexingStatus
from services.repository_memory.service import IndexingCoordinator

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_missing_workspace_fails_indexing_without_fake_source(tmp_path):
    job = SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
        repository_id=uuid4(),
        status=IndexingStatus.PENDING,
        commit_sha="HEAD",
        started_at=None,
        finished_at=None,
    )
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: job)),
        commit=AsyncMock(),
        rollback=AsyncMock(),
        add=Mock(),
        flush=AsyncMock(),
    )
    coordinator = IndexingCoordinator(cast("AsyncSession", session), SimpleNamespace(workspace_root=str(tmp_path)))

    await coordinator.execute_job(job.id)

    assert job.status == IndexingStatus.FAILED
    assert job.finished_at is not None
    session.rollback.assert_awaited_once()
