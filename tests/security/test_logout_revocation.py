from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from starlette.requests import Request

from services.auth import api as auth_api

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_logout_revokes_the_authenticated_server_session(monkeypatch):
    user_id, session_id = uuid4(), uuid4()
    monkeypatch.setattr("services.auth.jwt.decode_access_token", lambda token: {"session_id": str(session_id)})
    db_session = SimpleNamespace(user_id=user_id, is_active=True)
    session = SimpleNamespace(get=AsyncMock(return_value=db_session), commit=AsyncMock())
    request = Request({"type": "http", "method": "POST", "path": "/logout", "headers": [(b"authorization", b"Bearer signed-token")]})

    assert await auth_api.logout(request, {"id": str(user_id)}, cast("AsyncSession", session)) == {"status": "signed_out"}
    assert db_session.is_active is False
    session.commit.assert_awaited_once()
