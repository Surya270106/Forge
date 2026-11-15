import json

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from services.auth import api as auth_api


@pytest.mark.asyncio
async def test_login_exchange_consumes_code_once(monkeypatch):
    values = {"forge:login-exchange:valid": json.dumps({"token": "signed", "org_id": "org"})}

    class FakeRedis:
        async def getdel(self, key):
            return values.pop(key, None)

        async def aclose(self):
            pass

    monkeypatch.setattr(auth_api.redis_async, "from_url", lambda url: FakeRedis())
    server_request = Request({"type": "http", "method": "POST", "path": "/exchange", "headers": []})
    result = await auth_api.github_exchange(auth_api.LoginExchangeRequest(code="valid"), server_request)
    assert result == {"token": "signed", "org_id": "org"}
    with pytest.raises(HTTPException) as error:
        await auth_api.github_exchange(auth_api.LoginExchangeRequest(code="valid"), server_request)
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_browser_request_cannot_receive_exchange_token():
    browser_request = Request({"type": "http", "method": "POST", "path": "/exchange", "headers": [(b"origin", b"https://forgea1.vercel.app")]})
    with pytest.raises(HTTPException) as error:
        await auth_api.github_exchange(auth_api.LoginExchangeRequest(code="valid"), browser_request)
    assert error.value.status_code == 403
