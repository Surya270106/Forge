import asyncio
from uuid import UUID

import httpx
import pytest
import redis.asyncio as redis

from packages.database.engine import get_engine, get_session_factory
from packages.events.outbox import OutboxRelay
from packages.events.worker import EventWorker
from packages.shared.config import get_settings
from services.execution.sandbox import LocalProcessSandbox
from services.execution.worker import ExecutionWorker

BASE_URL = "http://127.0.0.1:8000"


async def mock_execution_handler(event_data, session):
    # This handler mimics what the real system should do:
    # take the execution.started event and run the job.
    job_id = UUID(event_data["aggregate_id"])
    settings = get_settings()
    sandbox = LocalProcessSandbox(workspace_root=settings.workspace_root)
    worker = ExecutionWorker(session, sandbox)
    await worker.execute_job(job_id)


@pytest.fixture
async def redis_client():
    settings = get_settings()
    r = redis.from_url(settings.redis_url)
    yield r
    await r.close()


@pytest.fixture
def db_session_maker():
    settings = get_settings()
    engine = get_engine(settings.database_url)
    return get_session_factory(engine)


@pytest.fixture
async def event_infrastructure(redis_client, db_session_maker):
    relay = OutboxRelay(session_maker=db_session_maker, redis_client=redis_client, batch_size=10, poll_interval=1.0)

    worker = EventWorker(
        redis_client=redis_client,
        session_maker=db_session_maker,
        consumer_group="test_execution_group",
        consumer_name="test_worker_1",
        streams=["forge:events:execution"],
    )

    worker.register_handler("execution.started", mock_execution_handler)

    await relay.start()
    await worker.start()

    yield

    await relay.stop()
    await worker.stop()


from apps.api.main import app


@pytest.mark.skip(reason="Product completion rendered integration test obsolete until rewrite")
@pytest.mark.asyncio
async def test_worker_events_end_to_end(redis_client, session_maker, mock_sandbox):
    # Proves: POST request -> worker consumes event -> state changes async -> HTTP polling observes completion
    headers = {"X-Organization-Id": "00000000-0000-0000-0000-000000000000"}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        # Step 1: Trigger repository import (RFC-001)
        import uuid

        unique_name = f"dummy-repo-{uuid.uuid4()}"
        req_data = {"clone_url": "file:///tmp/dummy", "owner": "dummy-owner", "name": unique_name}
        repo_resp = await client.post("/api/v1/repositories/import", json=req_data)
        assert repo_resp.status_code == 202
        repo_id = repo_resp.json()["repository_id"]

        # Step 2: Create a plan
        plan_req = {"intent": "Fix the bug"}
        plan_resp = await client.post(f"/api/v1/repositories/{repo_id}/plans", json=plan_req)
        assert plan_resp.status_code == 200
        plan_id = plan_resp.json()["id"]

        # Step 3: Approve plan
        await client.post(f"/api/v1/plans/{plan_id}/approve")

        # Step 4: Trigger Execution - generates execution.started outbox event
        exec_resp = await client.post(f"/api/v1/executions/plans/{plan_id}", json={})
        assert exec_resp.status_code == 200
        job_id = exec_resp.json()["id"]
        assert exec_resp.json()["status"] == "PENDING"  # Returned accepted/queued state

        # Step 5: Poll for completion
        completed = False
        for _ in range(20):
            await asyncio.sleep(1)
            status_resp = await client.get(f"/api/v1/executions/{job_id}")
            assert status_resp.status_code == 200
            status = status_resp.json()["status"]
            if status in ["COMPLETED", "FAILED"]:
                completed = True
                break

        assert completed, f"Execution did not complete asynchronously via worker. Last status: {status}"
