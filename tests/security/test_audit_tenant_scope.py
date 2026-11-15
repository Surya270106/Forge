from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from packages.shared.pagination import PaginationParams
from services.audit.api import list_organization_audit_logs, list_repository_audit_logs

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_organization_audit_rejects_other_tenant_before_query():
    session = SimpleNamespace(scalar=AsyncMock(), execute=AsyncMock())
    with pytest.raises(HTTPException) as error:
        await list_organization_audit_logs(
            uuid4(),
            PaginationParams(page_size=20, page=1),
            action=None,
            resource_type=None,
            tenant=uuid4(),
            session=cast("AsyncSession", session),
        )
    assert error.value.status_code == 404
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_repository_audit_query_is_scoped_to_tenant():
    tenant, repository = uuid4(), uuid4()
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=0),
        execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))),
    )
    await list_repository_audit_logs(
        repository,
        PaginationParams(page_size=20, page=1),
        action=None,
        resource_type=None,
        tenant=tenant,
        session=cast("AsyncSession", session),
    )
    query = session.execute.await_args.args[0]
    assert "audit_logs.organization_id" in str(query)
    assert tenant in query.compile().params.values()
