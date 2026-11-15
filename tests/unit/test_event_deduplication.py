import json
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from packages.events.worker import EventWorker

if TYPE_CHECKING:
    from redis.asyncio import Redis


@pytest.mark.asyncio
async def test_processed_event_uses_consumer_group_identity():
    organization_id, event_id = uuid4(), uuid4()
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None)),
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
    assert session.add.call_args.args[0].consumer_name == "forge_worker_group"
    redis.xack.assert_awaited_once()


@pytest.mark.asyncio
async def test_audit_failure_keeps_event_pending_for_retry():
    organization_id, event_id = uuid4(), uuid4()
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None)),
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
