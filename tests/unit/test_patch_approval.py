from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from packages.database.models.patch import PatchStatus
from services.patch.service import PatchService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_accept_patch_only_records_approval():
    organization_id = uuid4()
    patch = SimpleNamespace(
        organization_id=organization_id,
        status=PatchStatus.GENERATED,
        reviewed_at=None,
        reviewed_by=None,
        pull_request_url=None,
        branch_name=None,
        id=uuid4(),
    )
    session = SimpleNamespace(get=AsyncMock(return_value=patch), commit=AsyncMock())
    service = PatchService(cast("AsyncSession", session), organization_id)
    service.review_patch = AsyncMock(return_value={"review_digest": "a" * 64})
    result = await service.accept_patch(patch.id, "a" * 64, uuid4())

    assert result.status == PatchStatus.ACCEPTED
    assert result.pull_request_url is None
    assert result.branch_name is None
    session.commit.assert_awaited_once()
