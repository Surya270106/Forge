import json
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from packages.database.models.execution import ExecutionJobModel
from packages.shared.identifiers import OrganizationId
from services.execution.api import create_websocket_ticket

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_ticket_is_short_lived_and_scoped_to_owned_execution(monkeypatch):
    organization_id, job_id, user_id, session_id = uuid4(), uuid4(), uuid4(), uuid4()
    redis = SimpleNamespace(set=AsyncMock(return_value=True), aclose=AsyncMock())
    monkeypatch.setattr("redis.asyncio.from_url", lambda _url: redis)
    monkeypatch.setattr("services.auth.jwt.decode_access_token", lambda _token: {"sub": str(user_id), "session_id": str(session_id)})
    session = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(organization_id=organization_id)))
    request = Request({"type": "http", "method": "POST", "path": "/ws-ticket", "headers": [(b"cookie", b"forge_session=signed-token")]})

    response = await create_websocket_ticket(job_id, request, OrganizationId(organization_id), cast("AsyncSession", session))

    session.get.assert_awaited_once_with(ExecutionJobModel, job_id)
    args, kwargs = redis.set.await_args
    assert args[0] == f"forge:ws-ticket:{response['ticket']}"
    assert json.loads(args[1]) == {
        "job_id": str(job_id),
        "organization_id": str(organization_id),
        "user_id": str(user_id),
        "session_id": str(session_id),
    }
    assert kwargs == {"ex": 45, "nx": True}


@pytest.mark.asyncio
async def test_ticket_rejects_execution_from_another_organization():
    organization_id, job_id = uuid4(), uuid4()
    session = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(organization_id=uuid4())))
    request = Request({"type": "http", "method": "POST", "path": "/ws-ticket", "headers": []})
    with pytest.raises(HTTPException) as error:
        await create_websocket_ticket(job_id, request, OrganizationId(organization_id), cast("AsyncSession", session))
    assert error.value.status_code == 404
