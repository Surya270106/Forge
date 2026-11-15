import asyncio
import os
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
import redis.asyncio as redis_async
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database.models.outbox_event import OutboxEventModel
from packages.events.outbox import OutboxRelay


@pytest.mark.asyncio
async def test_unpublished_event_survives_redis_outage_and_publish_ack_crash():
    database_url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    redis_url = os.environ.get("FORGE_TEST_REDIS_URL")
    if not database_url or not redis_url:
        pytest.skip("Disposable PostgreSQL and Redis are required")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    redis_client = redis_async.from_url(redis_url)
    unavailable_redis = redis_async.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2)
    event_id = uuid4()
    stream = "forge:events:execution"
    try:
        async with sessions() as session:
            session.add(OutboxEventModel(
                id=event_id, event_type="execution.requested", organization_id=str(uuid4()),
                aggregate_type="execution", aggregate_id=str(uuid4()), payload={"job_id": str(uuid4())},
                occurred_at=datetime(2000, 1, 1, tzinfo=UTC), published=False,
            ))
            await session.commit()

        await OutboxRelay(sessions, unavailable_redis, batch_size=1)._process_batch()
        async with sessions() as session:
            event = await session.get(OutboxEventModel, event_id)
            assert event is not None and not event.published

        relay = OutboxRelay(sessions, redis_client, batch_size=1)
        original_publish = relay._publish_to_redis

        async def publish_then_crash(event):
            await original_publish(event)
            raise RuntimeError("simulated crash before outbox acknowledgement")

        relay._publish_to_redis = publish_then_crash
        await relay._process_batch()
        async with sessions() as session:
            event = await session.get(OutboxEventModel, event_id)
            assert event is not None and not event.published

        relay._publish_to_redis = original_publish
        await relay._process_batch()
        async with sessions() as session:
            event = await session.get(OutboxEventModel, event_id)
            assert event is not None and event.published
        entries = cast("list[tuple[bytes, dict[bytes, bytes]]]", await redis_client.xrange(stream))
        assert sum(data.get(b"event_id") == str(event_id).encode() for _, data in entries) == 2
    finally:
        await unavailable_redis.aclose()
        await redis_client.aclose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_relays_publish_one_copy_of_an_event():
    database_url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    redis_url = os.environ.get("FORGE_TEST_REDIS_URL")
    if not database_url or not redis_url:
        pytest.skip("Disposable PostgreSQL and Redis are required")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    redis_client = redis_async.from_url(redis_url)
    event_id = uuid4()
    entered = asyncio.Event()
    release = asyncio.Event()
    first = OutboxRelay(sessions, redis_client, batch_size=1)
    second = OutboxRelay(sessions, redis_client, batch_size=1)
    publish = first._publish_to_redis

    async def delayed_publish(event):
        entered.set()
        await release.wait()
        await publish(event)

    first._publish_to_redis = delayed_publish
    try:
        async with sessions() as session:
            session.add(OutboxEventModel(
                id=event_id, event_type="execution.requested", organization_id=str(uuid4()),
                aggregate_type="execution", aggregate_id=str(uuid4()), payload={"job_id": str(uuid4())},
                occurred_at=datetime(1999, 1, 1, tzinfo=UTC), published=False,
            ))
            await session.commit()
        first_task = asyncio.create_task(first._process_batch())
        await asyncio.wait_for(entered.wait(), timeout=5)
        await asyncio.wait_for(second._process_batch(), timeout=5)
        release.set()
        await first_task
        entries = cast("list[tuple[bytes, dict[bytes, bytes]]]", await redis_client.xrange("forge:events:execution"))
        assert sum(data.get(b"event_id") == str(event_id).encode() for _, data in entries) == 1
    finally:
        release.set()
        await redis_client.aclose()
        await engine.dispose()
