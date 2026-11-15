from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest
from fastapi import HTTPException

from services.auth.dependencies import authenticate_access_token
from services.auth.jwt import create_access_token

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_signed_token_without_server_session_is_rejected():
    token = create_access_token({"sub": str(uuid4()), "email": "test@example.invalid"})
    with pytest.raises(HTTPException) as error:
        await authenticate_access_token(token, cast("AsyncSession", object()))
    assert error.value.status_code == 401
