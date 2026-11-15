import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.main import app
from packages.database.engine import get_session
from packages.database.models.atlas import AtlasEdgeModel, AtlasJobModel, AtlasNodeModel, AtlasSnapshotModel
from packages.database.models.auth import OrganizationModel, RoleBindingModel, SessionModel, UserModel
from packages.database.models.execution import ExecutionEventModel, ExecutionJobModel, ExecutionStatus
from packages.database.models.planning import PlanModel, PlanStatus
from packages.database.models.repository import RepositoryModel, RepositoryStatus
from packages.database.tenant import set_system_context
from services.atlas.service import create_job, get_graph, impact_from_db, recover_stale_jobs, run_job
from services.auth.jwt import create_access_token


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          check=True, timeout=10).stdout.strip()


@pytest.mark.asyncio
async def test_atlas_snapshots_incremental_worker_idempotency_and_tenant_rls(tmp_path):
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Disposable migrated PostgreSQL required")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    org, other, owner, repo_id, plan_id, execution_id, browser_session_id = (uuid4() for _ in range(7))
    session_secret = str(uuid4())
    root = tmp_path / str(org) / str(repo_id)
    root.mkdir(parents=True)
    _git(root, "init", "-q")
    (root / "a.py").write_text("def add(): return 1\n")
    (root / "b.py").write_text("from a import add\ndef use(): return add()\n")
    _git(root, "add", "a.py", "b.py")
    _git(root, "-c", "user.name=Atlas", "-c", "user.email=atlas@example.invalid", "commit", "-qm", "base")
    set_system_context()
    try:
        async with sessions() as session:
            session.add_all([
                OrganizationModel(id=org, name=f"atlas-{org}"),
                OrganizationModel(id=other, name=f"atlas-{other}"),
                UserModel(id=owner, name="Atlas", email=f"atlas-{owner}@example.invalid"),
                RepositoryModel(id=repo_id, organization_id=org, owner="atlas", name="fixture",
                                full_name="atlas/fixture", clone_url="https://github.com/atlas/fixture.git",
                                status=RepositoryStatus.READY),
            ])
            await session.flush()
            session.add_all([
                RoleBindingModel(id=uuid4(), organization_id=org, user_id=owner, role="OWNER"),
                RoleBindingModel(id=uuid4(), organization_id=other, user_id=owner, role="OWNER"),
                SessionModel(id=browser_session_id, user_id=owner, session_token=session_secret,
                             expires_at=(datetime.now(UTC) + timedelta(hours=1)).replace(tzinfo=None)),
            ])
            session.add(PlanModel(id=plan_id, organization_id=org, repository_id=repo_id,
                                  status=PlanStatus.APPROVED, intent="Index source", context_snapshot={}))
            await session.flush()
            session.add(ExecutionJobModel(id=execution_id, organization_id=org, repository_id=repo_id,
                                          plan_id=plan_id, status=ExecutionStatus.COMPLETED,
                                          commit_sha_before=_git(root, "rev-parse", "HEAD")))
            await session.commit()
        key = uuid4()
        async with sessions() as session:
            with pytest.raises(ValueError, match="Execution unavailable"):
                await create_job(session, org, repo_id, owner, uuid4(), execution_id=uuid4())
            first = await create_job(session, org, repo_id, owner, key, execution_id=execution_id)
            assert (await create_job(session, org, repo_id, owner, key, execution_id=execution_id)).id == first.id
            await session.commit()
        await run_job(sessions, first.id, tmp_path)
        await run_job(sessions, first.id, tmp_path)  # Duplicate queue delivery is inert.
        async with sessions() as session:
            job = await session.get(AtlasJobModel, first.id)
            assert job is not None and job.status == "SUCCEEDED"
            before = (await session.execute(select(AtlasSnapshotModel).where(AtlasSnapshotModel.job_id == first.id))).scalar_one()
            assert before.status == "PUBLISHED" and not before.dirty
            assert before.commit_sha == _git(root, "rev-parse", "HEAD")
            assert before.tree_sha == _git(root, "rev-parse", "HEAD^{tree}")
            events = (await session.execute(select(ExecutionEventModel.event_type).where(
                ExecutionEventModel.execution_job_id == execution_id,
            ).order_by(ExecutionEventModel.sequence))).scalars().all()
            assert events == ["atlas.index_requested", "atlas.index_started", "atlas.files_parsed", "atlas.snapshot_published"]
            graph = await get_graph(session, org, repo_id, before.id)
            assert any(edge.kind == "IMPORTS" and edge.resolution == "RESOLVED_STATIC" for edge in graph.edges)
            impacted = await impact_from_db(session, org, repo_id, before.id, "file:a.py", max_depth=2, max_results=10)
            assert any(item.key == "file:b.py" for item in impacted.items)
            node_id = await session.scalar(select(AtlasNodeModel.id).where(AtlasNodeModel.snapshot_id == before.id))
            assert node_id
            assert await session.scalar(select(AtlasEdgeModel.id).where(AtlasEdgeModel.snapshot_id == before.id))
            with pytest.raises(ValueError):
                await get_graph(session, other, repo_id, before.id)

        async def api_session():
            async with sessions() as session:
                yield session

        token = create_access_token({"sub": str(owner), "session_id": str(browser_session_id),
                                     "session_token": session_secret})
        app.dependency_overrides[get_session] = api_session
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://atlas.test") as client:
                headers = {"Authorization": f"Bearer {token}", "X-Organization-Id": str(org)}
                prefix = f"/api/v1/repositories/{repo_id}/atlas"
                assert (await client.get(f"{prefix}/snapshots", headers=headers)).status_code == 200
                assert (await client.get(f"{prefix}/graph", params={"snapshot_id": str(before.id)}, headers=headers)).status_code == 200
                impact_path = f"{prefix}/impact"
                assert (await client.get(impact_path, params={"snapshot_id": str(before.id),
                                                              "node_key": "file:a.py", "kinds": "IMPORTS"},
                                         headers=headers)).status_code == 200
                assert (await client.get(impact_path, params={"snapshot_id": str(before.id),
                                                              "node_key": "file:a.py", "kinds": "DELETE"},
                                         headers=headers)).status_code == 422
                other_headers = {**headers, "X-Organization-Id": str(other)}
                for path in ("/snapshots", f"/jobs/{first.id}", f"/snapshots/{before.id}",
                             f"/graph?snapshot_id={before.id}", f"/symbols?snapshot_id={before.id}",
                             f"/impact?snapshot_id={before.id}&node_key=file:a.py",
                             f"/tests?snapshot_id={before.id}&node_key=file:a.py",
                             f"/diff?left={before.id}&right={before.id}", f"/nodes/{node_id}"):
                    assert (await client.get(f"{prefix}{path}", headers=other_headers)).status_code == 404
                assert (await client.post(f"{prefix}/index", headers=other_headers,
                                          json={"idempotency_key": str(uuid4())})).status_code == 404
        finally:
            app.dependency_overrides.pop(get_session, None)
            set_system_context()

        (root / "a.py").write_text("def add(): return 2\n")
        async with sessions() as session:
            second = await create_job(session, org, repo_id, owner, uuid4())
            await session.commit()
        await run_job(sessions, second.id, tmp_path)
        async with sessions() as session:
            after = (await session.execute(select(AtlasSnapshotModel).where(AtlasSnapshotModel.job_id == second.id))).scalar_one()
            assert after.status == "PUBLISHED" and after.dirty
            assert after.source_fingerprint != before.source_fingerprint
            assert after.stats["reused_files"] == 1
            assert (await session.get(AtlasSnapshotModel, before.id)).status == "PUBLISHED"
            stored = await session.get(AtlasSnapshotModel, before.id)
            assert stored is not None
            stored.stats = {"files": 0}
            with pytest.raises(DBAPIError):
                await session.commit()
            await session.rollback()

        async with sessions() as session:
            failed = await create_job(session, org, repo_id, owner, uuid4(), requested_revision="a" * 40,
                                      execution_id=execution_id)
            await session.commit()
        await run_job(sessions, failed.id, tmp_path)
        async with sessions() as session:
            failed_job = await session.get(AtlasJobModel, failed.id)
            assert failed_job is not None and failed_job.status == "FAILED"
            failure_events = (await session.execute(select(ExecutionEventModel).where(
                ExecutionEventModel.execution_job_id == execution_id,
                ExecutionEventModel.event_type == "atlas.index_failed",
            ))).scalars().all()
            assert len(failure_events) == 1 and failure_events[0].data["atlas_job_id"] == str(failed.id)
            assert await session.scalar(select(AtlasSnapshotModel.id).where(AtlasSnapshotModel.job_id == failed.id)) is None
            assert (await session.get(AtlasSnapshotModel, before.id)).status == "PUBLISHED"

        async with sessions() as session:
            stale = await create_job(session, org, repo_id, owner, uuid4())
            stale.status = "RUNNING"
            stale.attempts = 1
            stale.lease_owner = "old-worker"
            stale.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()
        async with sessions() as session:
            assert await recover_stale_jobs(session, org) == 1
            await session.commit()
        await run_job(sessions, stale.id, tmp_path)
        async with sessions() as session:
            recovered = await session.get(AtlasJobModel, stale.id)
            assert recovered is not None and recovered.status == "SUCCEEDED" and recovered.attempts == 2

        async with engine.begin() as connection:
            await connection.execute(text("""DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'forge_atlas_rls_test')
                THEN CREATE ROLE forge_atlas_rls_test NOLOGIN NOSUPERUSER NOBYPASSRLS; END IF; END $$"""))
            await connection.execute(text("GRANT USAGE ON SCHEMA public TO forge_atlas_rls_test"))
            await connection.execute(text("GRANT SELECT ON atlas_jobs, atlas_snapshots, atlas_nodes, atlas_edges, atlas_file_facts TO forge_atlas_rls_test"))
            await connection.execute(text("SET LOCAL ROLE forge_atlas_rls_test"))
            await connection.execute(text("SELECT set_config('forge.organization_id', :org, true)"), {"org": str(other)})
            assert (await connection.execute(text("SELECT id FROM atlas_snapshots WHERE id=:id"), {"id": before.id})).all() == []
            for table in ("atlas_jobs", "atlas_file_facts", "atlas_nodes", "atlas_edges"):
                assert (await connection.execute(text(f"SELECT id FROM {table} WHERE organization_id=:org LIMIT 1"),
                                                 {"org": org})).all() == []
    finally:
        await engine.dispose()
