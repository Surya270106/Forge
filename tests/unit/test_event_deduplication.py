import asyncio
import json
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from packages.events.worker import EventWorker

if TYPE_CHECKING:
    from redis.asyncio import Redis


@pytest.mark.asyncio
async def test_processed_event_uses_consumer_group_identity():
    organization_id, event_id = uuid4(), uuid4()
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: uuid4())),
        add=MagicMock(),
        commit=AsyncMock(),
    )

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args):
            return False

    redis = SimpleNamespace(xack=AsyncMock())
    worker = EventWorker(cast("Redis", redis), SessionContext, "forge_worker_group", "worker-two", ["forge:events:repair"])
    handler = AsyncMock()
    worker.register_handler("repair.attempted", handler)
    message = {
        b"event_type": b"repair.attempted",
        b"event_id": str(event_id).encode(),
        b"organization_id": str(organization_id).encode(),
        b"aggregate_id": str(uuid4()).encode(),
        b"payload": json.dumps({"verification_job_id": str(uuid4())}).encode(),
    }

    await worker._process_message("forge:events:repair", "1-0", message)

    handler.assert_awaited_once()
    reserved = session.execute.call_args.args[0]
    assert "forge_worker_group" in str(reserved.compile(compile_kwargs={"literal_binds": True}))
    redis.xack.assert_awaited_once()


@pytest.mark.asyncio
async def test_audit_failure_keeps_event_pending_for_retry():
    organization_id, event_id = uuid4(), uuid4()
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: uuid4())),
        add=MagicMock(),
        commit=AsyncMock(),
    )

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args):
            return False

    redis = SimpleNamespace(xack=AsyncMock())
    worker = EventWorker(cast("Redis", redis), SessionContext, "forge_worker_group", "worker-two", ["forge:events:repair"])
    audit_handler = AsyncMock(side_effect=RuntimeError("audit unavailable"))
    business_handler = AsyncMock()
    worker.register_global_handler(audit_handler)
    worker.register_handler("repair.attempted", business_handler)
    message = {
        b"event_type": b"repair.attempted",
        b"event_id": str(event_id).encode(),
        b"organization_id": str(organization_id).encode(),
        b"aggregate_id": str(uuid4()).encode(),
        b"payload": b"{}",
    }

    await worker._process_message("forge:events:repair", "1-0", message)

    audit_handler.assert_awaited_once()
    business_handler.assert_not_awaited()
    session.commit.assert_not_awaited()
    redis.xack.assert_not_awaited()


@pytest.mark.asyncio
async def test_handler_commit_cannot_commit_processed_marker_or_audit_projection():
    reservation = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: uuid4())),
        commit=AsyncMock(),
    )
    handler_session = SimpleNamespace(commit=AsyncMock())
    sessions = iter([reservation, handler_session])

    class SessionContext:
        async def __aenter__(self):
            return next(sessions)

        async def __aexit__(self, *_args):
            return False

    redis = SimpleNamespace(xack=AsyncMock())
    worker = EventWorker(cast("Redis", redis), SessionContext, "forge_worker_group", "worker", ["forge:events:execution"])
    audit = AsyncMock()

    async def handler(_event, session):
        assert session is handler_session
        await session.commit()
        reservation.commit.assert_not_awaited()

    worker.register_global_handler(audit)
    worker.register_handler("execution.requested", handler)
    message = {
        b"event_type": b"execution.requested", b"event_id": str(uuid4()).encode(),
        b"organization_id": str(uuid4()).encode(), b"aggregate_id": str(uuid4()).encode(), b"payload": b"{}",
    }
    await worker._process_message("forge:events:execution", "1-0", message)
    assert audit.await_args is not None
    assert audit.await_args.args[1] is reservation
    reservation.commit.assert_awaited_once()
    redis.xack.assert_awaited_once()


@pytest.mark.asyncio
async def test_redis_outage_during_pending_heartbeat_cancels_handler_without_ack():
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: uuid4())),
        commit=AsyncMock(),
    )

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args):
            return False

    redis = SimpleNamespace(xack=AsyncMock(), xclaim=AsyncMock(side_effect=RedisConnectionError("offline")))
    worker = EventWorker(cast("Redis", redis), SessionContext, "forge_worker_group", "worker", ["forge:events:execution"], pending_idle_ms=100)
    entered = asyncio.Event()

    async def handler(_event, _session):
        entered.set()
        await asyncio.Event().wait()

    worker.register_handler("execution.requested", handler)
    message = {
        b"event_type": b"execution.requested", b"event_id": str(uuid4()).encode(),
        b"organization_id": str(uuid4()).encode(), b"aggregate_id": str(uuid4()).encode(), b"payload": b"{}",
    }
    with pytest.raises(RuntimeError, match="ownership was lost"):
        await asyncio.wait_for(worker._process_message("forge:events:execution", "1-0", message), timeout=2)
    assert entered.is_set()
    session.commit.assert_not_awaited()
    redis.xack.assert_not_awaited()
