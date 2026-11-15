import asyncio
import os
import subprocess
import sys
from typing import cast
from uuid import uuid4

import pytest
import redis.asyncio as redis_async
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database.models.audit import AuditLogModel
from packages.database.models.auth import OrganizationModel
from packages.database.tenant import set_system_context
from packages.events.worker import EventWorker
from services.audit.worker import handle_audit_event


@pytest.mark.asyncio
async def test_process_killed_after_commit_before_ack_replays_without_duplicate_result():
    database_url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    redis_url = os.environ.get("FORGE_TEST_REDIS_URL")
    if not database_url or not redis_url:
        pytest.skip("Disposable PostgreSQL and Redis are required")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    redis_client = redis_async.from_url(redis_url)
    org_id, event_id, aggregate_id = uuid4(), uuid4(), uuid4()
    stream = f"forge:test:events:{uuid4()}"
    group = f"forge:test:consumers:{uuid4()}"
    child = None
    set_system_context()
    try:
        async with sessions() as session:
            session.add(OrganizationModel(id=org_id, name=f"ACK crash fixture {org_id}"))
            await session.commit()
        await redis_client.xgroup_create(stream, group, id="0", mkstream=True)
        await redis_client.xadd(stream, {
            "event_id": str(event_id), "event_type": "execution.requested", "organization_id": str(org_id),
            "aggregate_type": "execution", "aggregate_id": str(aggregate_id), "payload": "{}",
        })
        script = """
import asyncio, os, sys
from datetime import UTC, datetime
from uuid import UUID
import redis.asyncio as redis_async
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from packages.database.models.audit import AuditLogModel
from packages.events.worker import EventWorker
async def main():
    engine = create_async_engine(os.environ['FORGE_RLS_TEST_DATABASE_URL'])
    redis = redis_async.from_url(os.environ['FORGE_TEST_REDIS_URL'])
    worker = EventWorker(redis, async_sessionmaker(engine, expire_on_commit=False), sys.argv[2], 'crashed', [sys.argv[1]])
    async def handler(event, session):
        session.add(AuditLogModel(organization_id=UUID(event['organization_id']), action='event.persisted',
            actor_type='system', resource_type='execution', resource_id=UUID(event['aggregate_id']),
            metadata_payload={}, timestamp=datetime.now(UTC)))
        await session.commit()
    async def block_ack(*_args):
        print('persisted', flush=True)
        await asyncio.Event().wait()
    worker.register_handler('execution.requested', handler)
    redis.xack = block_ack
    result = await redis.xreadgroup(sys.argv[2], 'crashed', {sys.argv[1]: '>'}, count=1)
    message_id, message = result[0][1][0]
    await worker._process_message(sys.argv[1], message_id.decode(), message)
asyncio.run(main())
"""
        child = subprocess.Popen(
            [sys.executable, "-u", "-c", script, stream, group],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        assert child.stdout is not None
        marker = await asyncio.wait_for(asyncio.to_thread(child.stdout.readline), timeout=10)
        assert marker == "persisted\n", child.stderr.read() if child.poll() is not None and child.stderr else marker
        child.kill()
        assert await asyncio.to_thread(child.wait, 10) != 0
        replayed = []

        async def duplicate_handler(_event, _session):
            replayed.append(True)

        replacement = EventWorker(redis_client, sessions, group, "replacement", [stream], pending_idle_ms=1)
        replacement.register_handler("execution.requested", duplicate_handler)
        await asyncio.sleep(0.05)
        await replacement._recover_pending()
        assert replayed == []
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(AuditLogModel).where(
                AuditLogModel.organization_id == org_id, AuditLogModel.action == "event.persisted",
            )) == 1
        assert (await redis_client.xpending(stream, group))["pending"] == 0
    finally:
        if child is not None and child.poll() is None:
            child.kill()
            await asyncio.to_thread(child.wait, 10)
        await redis_client.aclose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_active_message_is_not_reclaimed_by_second_consumer():
    database_url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    redis_url = os.environ.get("FORGE_TEST_REDIS_URL")
    if not database_url or not redis_url:
        pytest.skip("Disposable PostgreSQL and Redis are required")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    redis_client = redis_async.from_url(redis_url)
    org_id, event_id = uuid4(), uuid4()
    stream = f"forge:test:events:{uuid4()}"
    group = f"forge:test:consumers:{uuid4()}"
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def handler(event, _session):
        calls.append(event["event_id"])
        entered.set()
        await release.wait()

    workers = [
        EventWorker(redis_client, sessions, group, f"worker-{index}", [stream], pending_idle_ms=1000)
        for index in range(2)
    ]
    for worker in workers:
        worker.register_handler("execution.requested", handler)
    set_system_context()
    try:
        async with sessions() as session:
            session.add(OrganizationModel(id=org_id, name=f"Event ownership fixture {org_id}"))
            await session.commit()
        await workers[0].start()
        await redis_client.xadd(stream, {
            "event_id": str(event_id), "event_type": "execution.requested", "organization_id": str(org_id),
            "aggregate_id": str(uuid4()), "payload": "{}",
        })
        await asyncio.wait_for(entered.wait(), timeout=5)
        await workers[1].start()
        await asyncio.sleep(2)
        assert calls == [str(event_id)]
    finally:
        release.set()
        await asyncio.gather(*(worker.stop() for worker in workers))
        await redis_client.aclose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_duplicate_event_id_has_one_handler_across_consumers():
    database_url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    redis_url = os.environ.get("FORGE_TEST_REDIS_URL")
    if not database_url or not redis_url:
        pytest.skip("Disposable PostgreSQL and Redis are required")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    redis_client = redis_async.from_url(redis_url)
    org_id, event_id = uuid4(), uuid4()
    stream = f"forge:test:events:{uuid4()}"
    group = f"forge:test:consumers:{uuid4()}"
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def handler(event, _session):
        calls.append(event["event_id"])
        entered.set()
        await release.wait()

    workers = [EventWorker(redis_client, sessions, group, f"worker-{i}", [stream]) for i in range(2)]
    for worker in workers:
        worker.register_handler("execution.requested", handler)
    aggregate_id = str(uuid4())
    set_system_context()
    try:
        async with sessions() as session:
            session.add(OrganizationModel(id=org_id, name=f"Duplicate event fixture {org_id}"))
            await session.commit()
        await workers[0].start()
        await redis_client.xadd(stream, {
            "event_id": str(event_id), "event_type": "execution.requested", "organization_id": str(org_id),
            "aggregate_id": aggregate_id, "payload": "{}",
        })
        await asyncio.wait_for(entered.wait(), timeout=5)
        await workers[1].start()
        await redis_client.xadd(stream, {
            "event_id": str(event_id), "event_type": "execution.requested", "organization_id": str(org_id),
            "aggregate_id": aggregate_id, "payload": "{}",
        })
        await asyncio.sleep(0.5)
        assert calls == [str(event_id)]
    finally:
        release.set()
        await asyncio.gather(*(worker.stop() for worker in workers))
        await redis_client.aclose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_committed_handler_is_not_repeated_after_ack_failure(monkeypatch):
    database_url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    redis_url = os.environ.get("FORGE_TEST_REDIS_URL")
    if not database_url or not redis_url:
        pytest.skip("Disposable PostgreSQL and Redis are required")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    redis_client = redis_async.from_url(redis_url)
    org_id, event_id = uuid4(), uuid4()
    stream = f"forge:test:events:{uuid4()}"
    group = f"forge:test:consumers:{uuid4()}"
    calls = []

    async def handler(event, _session):
        calls.append(event["event_id"])

    worker = EventWorker(redis_client, sessions, group, "worker", [stream])
    worker.register_handler("execution.requested", handler)
    set_system_context()
    try:
        async with sessions() as session:
            session.add(OrganizationModel(id=org_id, name=f"Ack failure fixture {org_id}"))
            await session.commit()
        await redis_client.xgroup_create(stream, group, id="0", mkstream=True)
        await redis_client.xadd(stream, {
            "event_id": str(event_id), "event_type": "execution.requested", "organization_id": str(org_id),
            "aggregate_id": str(uuid4()), "payload": "{}",
        })
        result = cast(
            "list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]]",
            await redis_client.xreadgroup(group, "worker", {stream: ">"}, count=1),
        )
        message_id, message = result[0][1][0]
        original_ack = redis_client.xack
        attempts = 0

        async def fail_ack_once(*args):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise ConnectionError("simulated Redis acknowledgement outage")
            return await original_ack(*args)

        monkeypatch.setattr(redis_client, "xack", fail_ack_once)
        await worker._process_message(stream, message_id.decode(), message)
        assert len(calls) == 1
        pending = await redis_client.xpending(stream, group)
        assert isinstance(pending, dict) and pending["pending"] == 1
        await worker._process_message(stream, message_id.decode(), message)
        assert len(calls) == 1
        pending = await redis_client.xpending(stream, group)
        assert isinstance(pending, dict) and pending["pending"] == 0
    finally:
        await redis_client.aclose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_unowned_pending_event_is_reclaimed_after_worker_crash():
    database_url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    redis_url = os.environ.get("FORGE_TEST_REDIS_URL")
    if not database_url or not redis_url:
        pytest.skip("Disposable PostgreSQL and Redis are required")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    redis_client = redis_async.from_url(redis_url)
    org_id, event_id = uuid4(), uuid4()
    stream = f"forge:test:events:{uuid4()}"
    group = f"forge:test:consumers:{uuid4()}"
    calls = []

    async def handler(event, _session):
        calls.append(event["event_id"])

    replacement = EventWorker(redis_client, sessions, group, "replacement", [stream], pending_idle_ms=1)
    replacement.register_handler("execution.requested", handler)
    set_system_context()
    try:
        async with sessions() as session:
            session.add(OrganizationModel(id=org_id, name=f"Crash recovery fixture {org_id}"))
            await session.commit()
        await redis_client.xgroup_create(stream, group, id="0", mkstream=True)
        await redis_client.xadd(stream, {
            "event_id": str(event_id), "event_type": "execution.requested", "organization_id": str(org_id),
            "aggregate_id": str(uuid4()), "payload": "{}",
        })
        assert await redis_client.xreadgroup(group, "crashed", {stream: ">"}, count=1)
        await asyncio.sleep(0.05)
        await replacement._recover_pending()
        assert calls == [str(event_id)]
        pending = await redis_client.xpending(stream, group)
        assert isinstance(pending, dict) and pending["pending"] == 0
    finally:
        await redis_client.aclose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_handler_commit_before_crash_does_not_mark_event_processed():
    database_url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    redis_url = os.environ.get("FORGE_TEST_REDIS_URL")
    if not database_url or not redis_url:
        pytest.skip("Disposable PostgreSQL and Redis are required")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    redis_client = redis_async.from_url(redis_url)
    org_id, event_id = uuid4(), uuid4()
    stream = f"forge:test:events:{uuid4()}"
    group = f"forge:test:consumers:{uuid4()}"
    calls = 0

    async def handler(_event, session):
        nonlocal calls
        calls += 1
        await session.commit()
        if calls == 1:
            raise RuntimeError("simulated crash after intermediate state commit")

    worker = EventWorker(redis_client, sessions, group, "worker", [stream])
    worker.register_handler("execution.requested", handler)
    worker.register_global_handler(handle_audit_event)
    set_system_context()
    try:
        async with sessions() as session:
            session.add(OrganizationModel(id=org_id, name=f"Early commit fixture {org_id}"))
            await session.commit()
        await redis_client.xgroup_create(stream, group, id="0", mkstream=True)
        await redis_client.xadd(stream, {
            "event_id": str(event_id), "event_type": "execution.requested", "organization_id": str(org_id),
            "aggregate_type": "execution", "aggregate_id": str(uuid4()), "payload": "{}",
        })
        result = cast(
            "list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]]",
            await redis_client.xreadgroup(group, "worker", {stream: ">"}, count=1),
        )
        message_id, message = result[0][1][0]
        await worker._process_message(stream, message_id.decode(), message)
        await worker._process_message(stream, message_id.decode(), message)
        assert calls == 2
        async with sessions() as session:
            audit_count = await session.scalar(select(func.count()).select_from(AuditLogModel).where(
                AuditLogModel.organization_id == org_id,
                AuditLogModel.action == "execution.requested",
            ))
            assert audit_count == 1
        pending = await redis_client.xpending(stream, group)
        assert isinstance(pending, dict) and pending["pending"] == 0
    finally:
        await redis_client.aclose()
        await engine.dispose()
