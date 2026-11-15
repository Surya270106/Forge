import asyncio
import os
from uuid import uuid4

import pytest
import redis.asyncio as redis_async
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from apps.api.main import app
from packages.shared.config import ForgeSettings
from services.auth.rate_limit import RateLimitError, _client_ip, consume_rate_limit


@pytest.mark.asyncio
async def test_concurrent_clients_share_atomic_redis_limit():
    url = os.environ.get("FORGE_TEST_REDIS_URL")
    if not url:
        pytest.skip("FORGE_TEST_REDIS_URL is required")
    clients = [redis_async.from_url(url), redis_async.from_url(url)]
    key = f"forge:test:limit:{uuid4()}"
    try:
        async def attempt(index):
            try:
                await consume_rate_limit(clients[index % 2], [key], [5], 5)
                return True
            except RateLimitError:
                return False

        assert sum(await asyncio.gather(*(attempt(i) for i in range(50)))) == 5
        with pytest.raises(RateLimitError) as error:
            await consume_rate_limit(clients[1], [key], [5], 5)
        assert 1 <= error.value.retry_after <= 5
    finally:
        await asyncio.gather(*(client.aclose() for client in clients))


@pytest.mark.asyncio
async def test_auth_endpoint_returns_429_and_fails_closed_on_redis_outage(monkeypatch):
    url = os.environ.get("FORGE_TEST_REDIS_URL")
    if not url:
        pytest.skip("FORGE_TEST_REDIS_URL is required")
    monkeypatch.setenv("REDIS_URL", url)
    monkeypatch.setenv("RATE_LIMIT_AUTH", "2")
    monkeypatch.setenv("SECRET_KEY", str(uuid4()))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        statuses = [(await client.post("/api/v1/auth/github/exchange", json={"code": "invalid"})).status_code for _ in range(3)]
        assert statuses == [400, 400, 429]
        limited = await client.post("/api/v1/auth/github/exchange", json={"code": "invalid"})
        assert int(limited.headers["Retry-After"]) > 0

        monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
        unavailable = await client.post("/api/v1/auth/github/exchange", json={"code": "invalid"})
        assert unavailable.status_code == 503


@pytest.mark.asyncio
async def test_organization_limit_is_shared_by_distinct_users_and_resets():
    url = os.environ.get("FORGE_TEST_REDIS_URL")
    if not url:
        pytest.skip("FORGE_TEST_REDIS_URL is required")
    client = redis_async.from_url(url)
    org_key = f"forge:test:org:{uuid4()}"
    try:
        for _ in range(3):
            await consume_rate_limit(client, [f"forge:test:user:{uuid4()}", org_key], [1, 3], 1)
        with pytest.raises(RateLimitError):
            await consume_rate_limit(client, [f"forge:test:user:{uuid4()}", org_key], [1, 3], 1)
        await asyncio.sleep(1.1)
        await consume_rate_limit(client, [f"forge:test:user:{uuid4()}", org_key], [1, 3], 1)
    finally:
        await client.aclose()


def test_forwarded_ip_requires_configured_trusted_peer():
    request = Request({
        "type": "http", "method": "GET", "path": "/", "client": ("127.0.0.1", 1234),
        "headers": [(b"x-forwarded-for", b"198.51.100.1")],
    })
    assert _client_ip(request, ForgeSettings(trusted_proxy_cidrs=[])) == "127.0.0.1"
    assert _client_ip(request, ForgeSettings(trusted_proxy_cidrs=["127.0.0.1/32"])) == "198.51.100.1"
