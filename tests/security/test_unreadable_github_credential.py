from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
from typing import cast

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from packages.shared.crypto import CryptoService
from services.auth.dependencies import authenticate_access_token, require_github_token
from services.auth.jwt import create_access_token
from services.auth.api import logout
from starlette.requests import Request


@pytest.mark.asyncio
@pytest.mark.parametrize("credential", [None, "malformed-ciphertext"])
async def test_session_survives_unreadable_github_credential(credential):
    user_id, session_id = uuid4(), uuid4()
    session_secret = "opaque-test-session"
    db_session = SimpleNamespace(
        id=session_id, user_id=user_id, session_token=session_secret,
        is_active=True, expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
    )
    db_user = SimpleNamespace(id=user_id, email="test@example.invalid", name="Test", is_active=True, github_token=credential)
    db = SimpleNamespace(execute=AsyncMock(side_effect=[
        SimpleNamespace(scalar_one_or_none=lambda: db_session),
        SimpleNamespace(scalar_one_or_none=lambda: db_user),
    ]), get=AsyncMock(return_value=db_user))
    token = create_access_token({"sub": str(user_id), "session_id": str(session_id), "session_token": session_secret})
    authenticated = await authenticate_access_token(token, cast(AsyncSession, db))
    assert authenticated["id"] == str(user_id)
    with pytest.raises(HTTPException) as error:
        await require_github_token(authenticated, cast(AsyncSession, db))
    assert error.value.status_code == 401
    assert "Reconnect GitHub" in error.value.detail
    assert credential not in error.value.detail if credential else True

    db.get = AsyncMock(return_value=db_session)
    db.commit = AsyncMock()
    request = Request({"type": "http", "method": "POST", "path": "/logout",
                       "headers": [(b"authorization", f"Bearer {token}".encode())]})
    assert await logout(request, authenticated, cast(AsyncSession, db)) == {"status": "signed_out"}
    assert db_session.is_active is False
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_valid_github_credential_decrypts_only_when_required():
    user_id = uuid4()
    credential = CryptoService.encrypt("github-test-token")
    db = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(github_token=credential)))
    assert await require_github_token({"id": str(user_id)}, cast(AsyncSession, db)) == "github-test-token"
