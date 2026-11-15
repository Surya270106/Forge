"""Shared, fail-closed API limits for abuse-sensitive operations."""

import hashlib
import hmac
from ipaddress import ip_address, ip_network

import redis.asyncio as redis_async
from fastapi import Depends, HTTPException, Request

from packages.shared.config import ForgeSettings, get_settings
from services.auth.dependencies import get_current_user

_CONSUME = """
for i = 1, #KEYS do
  if tonumber(redis.call('GET', KEYS[i]) or '0') >= tonumber(ARGV[i + 1]) then
    return {0, math.max(redis.call('TTL', KEYS[i]), 1), 0}
  end
end
local remaining = 2147483647
for i = 1, #KEYS do
  local count = redis.call('INCR', KEYS[i])
  if count == 1 then redis.call('EXPIRE', KEYS[i], ARGV[1]) end
  remaining = math.min(remaining, tonumber(ARGV[i + 1]) - count)
end
return {1, 0, remaining}
"""


class RateLimitError(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after


async def consume_rate_limit(client: redis_async.Redis, keys: list[str], limits: list[int], window_seconds: int) -> int:
    if not keys or len(keys) != len(limits) or min(limits) < 1 or window_seconds < 1:
        raise ValueError("Invalid rate-limit configuration")
    allowed, retry_after, remaining = await client.eval(_CONSUME, len(keys), *keys, window_seconds, *limits)
    if not allowed:
        raise RateLimitError(int(retry_after))
    return int(remaining)


def _key(settings: ForgeSettings, category: str, dimension: str, identity: str) -> str:
    digest = hmac.new(
        settings.secret_key.get_secret_value().encode(), f"{dimension}:{identity}".encode(), hashlib.sha256
    ).hexdigest()
    return f"forge:ratelimit:{category}:{digest}"


def _client_ip(request: Request, settings: ForgeSettings) -> str:
    peer = request.client.host if request.client else "unknown"
    try:
        trusted = [ip_network(value) for value in settings.trusted_proxy_cidrs]
        if not any(ip_address(peer) in network for network in trusted):
            return peer
        forwarded = request.headers.get("x-forwarded-for", "")
        for value in reversed(forwarded.split(",")):
            candidate = value.strip()
            address = ip_address(candidate)
            if not any(address in network for network in trusted):
                return candidate
    except ValueError:
        pass
    return peer


async def enforce_rate_limit(category: str, identities: list[tuple[str, str]]) -> None:
    settings = get_settings()
    limit = getattr(settings, f"rate_limit_{category}")
    keys = [_key(settings, category, dimension, identity) for dimension, identity in identities]
    limits = [limit * 3 if dimension == "organization" else limit for dimension, _ in identities]
    client = redis_async.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=2)
    try:
        try:
            await consume_rate_limit(client, keys, limits, settings.rate_limit_window_seconds)
        except RateLimitError as error:
            raise HTTPException(status_code=429, detail="Too many requests", headers={"Retry-After": str(error.retry_after)}) from None
        except (redis_async.RedisError, OSError, TimeoutError):
            raise HTTPException(status_code=503, detail="Rate limiting unavailable", headers={"Retry-After": "5"}) from None
    finally:
        await client.aclose()


def limit_ip(category: str):
    async def check(request: Request) -> None:
        settings = get_settings()
        await enforce_rate_limit(category, [("ip", _client_ip(request, settings))])
    return check


def limit_user(category: str):
    async def check(user: dict = Depends(get_current_user)) -> None:
        await enforce_rate_limit(category, [("user", user["id"])])
    return check
