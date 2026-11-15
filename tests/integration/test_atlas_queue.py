import asyncio
import os
import subprocess
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import redis.asyncio as redis_async
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database.models.atlas import AtlasJobModel, AtlasSnapshotModel
from packages.database.models.auth import OrganizationModel, UserModel
from packages.database.models.repository import RepositoryModel, RepositoryStatus
from packages.database.tenant import set_system_context
from packages.events.outbox import OutboxRelay
from packages.events.worker import EventWorker
from services.atlas.service import create_job, run_job


@pytest.mark.asyncio
async def test_atlas_job_flows_through_outbox_redis_and_worker(tmp_path: Path):
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    redis_url = os.environ.get("FORGE_ATLAS_TEST_REDIS_URL")
    if not url or not redis_url:
        pytest.skip("Disposable migrated PostgreSQL and isolated Redis required")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    redis = redis_async.from_url(redis_url)
    org, owner, repo = (uuid4() for _ in range(3))
    workspace = tmp_path / str(org) / str(repo)
    workspace.mkdir(parents=True)
    subprocess.run(["git", "-C", str(workspace), "init", "-q"], check=True)
    (workspace / "main.py").write_text("def ready(): return True\n")
    subprocess.run(["git", "-C", str(workspace), "add", "main.py"], check=True)
    subprocess.run(["git", "-C", str(workspace), "-c", "user.name=Atlas", "-c",
                    "user.email=atlas@example.invalid", "commit", "-qm", "fixture"], check=True)
    set_system_context()
    async with sessions() as session:
        session.add_all([
            OrganizationModel(id=org, name=f"atlas-queue-{org}"),
            UserModel(id=owner, name="Atlas", email=f"atlas-queue-{owner}@example.invalid"),
            RepositoryModel(id=repo, organization_id=org, owner="atlas", name="queue",
                            full_name="atlas/queue", clone_url="https://example.invalid/queue.git",
                            status=RepositoryStatus.READY),
        ])
        await session.commit()
    async with sessions() as session:
        job = await create_job(session, org, repo, owner, uuid4())
        job_id = job.id
        await session.commit()

    worker = EventWorker(redis, sessions, f"atlas-test-{uuid4()}", "atlas-test", ["forge:events:repository"])

    async def index(event_data: dict, session):
        payload = event_data["payload"]
        if isinstance(payload, str):
            import json
            payload = json.loads(payload)
        if UUID(payload["job_id"]) != job_id:
            return
        await run_job(sessions, job_id, tmp_path)

    worker.register_handler("repository.atlas.index_requested", index)
    relay = OutboxRelay(sessions, redis, poll_interval=0.1)
    try:
        await worker.start()
        await relay.start()
        async with asyncio.timeout(30):
            while True:
                async with sessions() as session:
                    current = await session.get(AtlasJobModel, job_id)
                    if current and current.status in {"SUCCEEDED", "FAILED"}:
                        assert current.status == "SUCCEEDED", current.error_code
                        snapshots = (await session.execute(select(AtlasSnapshotModel).where(
                            AtlasSnapshotModel.job_id == job_id))).scalars().all()
                        assert len(snapshots) == 1 and snapshots[0].status == "PUBLISHED"
                        break
                await asyncio.sleep(0.2)
    finally:
        await relay.stop()
        await worker.stop()
        await redis.aclose()
        await engine.dispose()
