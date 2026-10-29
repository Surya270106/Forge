from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest

from packages.database.tenant import clear_tenant, get_tenant
from services.auth.dependencies import _verify_and_set_tenant

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_permission_check_sets_rls_value_in_existing_transaction():
    organization_id, user_id = uuid4(), uuid4()
    statements = []

    async def execute(statement, parameters=None):
        statements.append((statement, parameters))
        return SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(role="OWNER"))

    try:
        result = await _verify_and_set_tenant(
            None,
            str(organization_id),
            {"id": str(user_id)},
            cast("AsyncSession", SimpleNamespace(execute=execute)),
            None,
        )
        assert result == organization_id
        assert get_tenant() == organization_id
        assert len(statements) == 2
        assert "set_config('forge.organization_id'" in str(statements[0][0])
        assert statements[0][1] == {"organization_id": str(organization_id)}
        assert "role_bindings" in str(statements[1][0])
    finally:
        clear_tenant()
