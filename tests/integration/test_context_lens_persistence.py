import os
from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.main import app
from packages.database.engine import get_session
from packages.database.models.atlas import AtlasEdgeModel, AtlasJobModel, AtlasNodeModel, AtlasSnapshotModel
from packages.database.models.auth import OrganizationModel, RoleBindingModel, SessionModel, UserModel
from packages.database.models.context_lens import ContextChangeSetModel
from packages.database.models.execution import ExecutionJobModel, ExecutionStatus, MutationModel
from packages.database.models.patch import PatchStatus
from packages.database.models.planning import PlanModel, PlanStatus
from packages.database.models.repository import RepositoryModel, RepositoryStatus
from packages.database.models.verification import VerificationJobModel, VerificationResultModel, VerificationStatus
from packages.database.tenant import set_system_context
from services.auth.jwt import create_access_token
from services.patch.service import PatchService


@pytest.mark.asyncio
async def test_patch_preparation_captures_immutable_evidence_and_api_enforces_tenant():
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Disposable migrated PostgreSQL required")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    org, other, user_id, repo_id, plan_id, execution_id, browser_id, mutation_id, task_id = (uuid4() for _ in range(9))
    token_secret = str(uuid4())
    snapshot_id = uuid4()
    set_system_context()
    try:
        async with sessions() as session:
            session.add_all([
                OrganizationModel(id=org, name=f"lens-{org}"),
                OrganizationModel(id=other, name=f"lens-{other}"),
                UserModel(id=user_id, name="Lens", email=f"lens-{user_id}@example.invalid"),
                RepositoryModel(id=repo_id, organization_id=org, owner="lens", name="fixture",
                                full_name="lens/fixture", clone_url="https://github.com/lens/fixture.git",
                                status=RepositoryStatus.READY, commit_sha="a" * 40),
            ])
            await session.flush()
            session.add_all([
                RoleBindingModel(id=uuid4(), organization_id=org, user_id=user_id, role="OWNER"),
                RoleBindingModel(id=uuid4(), organization_id=other, user_id=user_id, role="OWNER"),
                SessionModel(id=browser_id, user_id=user_id, session_token=token_secret,
                             expires_at=(datetime.now(UTC) + timedelta(hours=1)).replace(tzinfo=None)),
                PlanModel(id=plan_id, organization_id=org, repository_id=repo_id, status=PlanStatus.APPROVED,
                          intent="Edit source", context_snapshot={}),
            ])
            await session.flush()
            session.add(ExecutionJobModel(id=execution_id, organization_id=org, repository_id=repo_id,
                                          plan_id=plan_id, status=ExecutionStatus.COMPLETED,
                                          commit_sha_before="a" * 40))
            await session.flush()
            from packages.database.models.planning import TaskNodeModel
            session.add(TaskNodeModel(id=task_id, organization_id=org, plan_id=plan_id,
                                      action_type="edit_file", target="src/example.py", parameters={}))
            await session.flush()
            session.add(MutationModel(id=mutation_id, organization_id=org, repository_id=repo_id,
                                      execution_job_id=execution_id, task_node_id=task_id,
                                      file_path="src/example.py", mutation_type="UPDATE",
                                      diff_hunk="--- src/example.py\n+++ src/example.py\n@@ -1 +1 @@\n-before\n+after\n"))
            await session.commit()

        async with sessions() as session:
            atlas_job_id = uuid4()
            session.add(AtlasJobModel(id=atlas_job_id, organization_id=org, repository_id=repo_id,
                                      requested_by=user_id, idempotency_key=uuid4(), status="SUCCEEDED", attempts=1))
            await session.flush()
            snapshot = AtlasSnapshotModel(id=snapshot_id, organization_id=org, repository_id=repo_id,
                                          job_id=atlas_job_id, commit_sha="a" * 40, tree_sha="b" * 40,
                                          source_fingerprint="c" * 64, dirty=False, indexer_version="atlas-5",
                                          parser_versions={}, config_fingerprint="d" * 64, status="BUILDING",
                                          stats={}, warnings=[], completed_at=datetime.now(UTC))
            session.add(snapshot)
            await session.flush()
            source, dependent, test_file, symbol = (uuid4() for _ in range(4))
            session.add_all([
                AtlasNodeModel(id=source, organization_id=org, repository_id=repo_id, snapshot_id=snapshot_id,
                               stable_key="file:src/example.py", kind="file", name="src/example.py", path="src/example.py"),
                AtlasNodeModel(id=dependent, organization_id=org, repository_id=repo_id, snapshot_id=snapshot_id,
                               stable_key="file:src/use.py", kind="file", name="src/use.py", path="src/use.py"),
                AtlasNodeModel(id=test_file, organization_id=org, repository_id=repo_id, snapshot_id=snapshot_id,
                               stable_key="file:tests/test_example.py", kind="test_file", name="tests/test_example.py", path="tests/test_example.py"),
                AtlasNodeModel(id=symbol, organization_id=org, repository_id=repo_id, snapshot_id=snapshot_id,
                               stable_key="symbol:src/example.py:function:change", kind="function", name="change",
                               path="src/example.py", line_start=1, line_end=2),
            ])
            await session.flush()
            for edge_id, origin, kind, path in ((uuid4(), dependent, "IMPORTS", "src/use.py"),
                                                (uuid4(), test_file, "TESTS", "tests/test_example.py")):
                session.add(AtlasEdgeModel(id=edge_id, organization_id=org, repository_id=repo_id,
                                           snapshot_id=snapshot_id, from_node_id=origin, to_node_id=source,
                                           kind=kind, target_name="example", evidence_path=path, evidence_line=1,
                                           resolution="RESOLVED_STATIC" if kind == "IMPORTS" else "INFERRED",
                                           confidence="HIGH" if kind == "IMPORTS" else "MEDIUM", method="fixture"))
            await session.flush()
            snapshot.status = "PUBLISHED"
            await session.commit()

        async with sessions() as session:
            patch = await PatchService(session, org).generate_patch(execution_id)
            change = (await session.execute(select(ContextChangeSetModel).where(
                ContextChangeSetModel.patch_id == patch.id))).scalar_one()
            assert change.review_digest == patch.review_digest
            assert change.base_snapshot_id == snapshot_id
            assert change.file_changes[0]["task_node_id"] == str(task_id)
            assert "-before" not in str(change.file_changes) and "+after" not in str(change.file_changes)
            assert (await PatchService(session, org).generate_patch(execution_id)).id == patch.id
            assert len((await session.execute(select(ContextChangeSetModel).where(
                ContextChangeSetModel.patch_id == patch.id))).scalars().all()) == 1

        async with sessions() as session:
            verification_id = uuid4()
            session.add(VerificationJobModel(id=verification_id, organization_id=org, repository_id=repo_id,
                                             execution_job_id=execution_id, status=VerificationStatus.FAILED))
            await session.flush()
            session.add_all([
                VerificationResultModel(id=uuid4(), organization_id=org, verification_job_id=verification_id,
                                        execution_id=execution_id, verifier="pytest", status=VerificationStatus.FAILED,
                                        exit_code=1, stdout="secret-test-output", diagnostics=[], blocking=True, attempt=1),
                VerificationResultModel(id=uuid4(), organization_id=org, verification_job_id=verification_id,
                                        execution_id=execution_id, verifier="optional", status=VerificationStatus.SKIPPED,
                                        exit_code=None, diagnostics=[], blocking=False, attempt=1),
            ])
            await session.commit()

        async def api_session():
            async with sessions() as session:
                yield session

        app.dependency_overrides[get_session] = api_session
        try:
            jwt = create_access_token({"sub": str(user_id), "session_id": str(browser_id),
                                       "session_token": token_secret})
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://lens.test") as client:
                path = f"/api/v1/executions/{execution_id}/context"
                headers = {"Authorization": f"Bearer {jwt}", "X-Organization-Id": str(org)}
                started = perf_counter()
                response = await client.get(path, headers=headers)
                print(f"Context Lens fixture read: {(perf_counter() - started) * 1000:.1f} ms, {len(response.content)} bytes")
                assert response.status_code == 200, response.text
                assert len(response.content) < 100_000
                body = response.json()
                assert body["change_set"]["files"][0]["path"] == "src/example.py"
                assert body["verification"]["summary"]["executed_commands"] == 1
                assert body["verification"]["summary"]["failed_commands"] == 1
                assert body["verification"]["summary"]["skipped_commands"] == 1
                assert body["verification"]["summary"]["selected_tests"] is None
                assert body["review"]["approved"] is False
                assert body["atlas"]["base_snapshot_id"] == str(snapshot_id)
                assert body["atlas"]["direct_symbols"][0]["name"] == "change"
                assert any(item["node_key"] == "file:src/use.py" for item in body["atlas"]["impacted"])
                assert any(item["node_key"] == "file:tests/test_example.py" for item in body["atlas"]["relevant_tests"])
                assert body["verification"]["summary"]["relevant_tests"] == 1
                assert "-before" not in response.text and "+after" not in response.text
                assert "secret-test-output" not in response.text
                assert (await client.get(path, headers={**headers, "X-Organization-Id": str(other)})).status_code == 404
                assert (await client.get(f"/api/v1/executions/{uuid4()}/context", headers=headers)).status_code == 404

            async with sessions() as session:
                mutable_patch = await session.get(type(patch), patch.id)
                mutable_patch.status = PatchStatus.ACCEPTED
                mutable_patch.reviewed_by = user_id
                mutation = await session.get(MutationModel, mutation_id)
                mutation.diff_hunk = mutation.diff_hunk.replace("+after", "+different")
                await session.commit()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://lens.test") as client:
                response = await client.get(path, headers=headers)
                assert response.status_code == 200, response.text
                assert response.json()["review"]["current"] is False
                assert response.json()["review"]["approved"] is False

            async with sessions() as session:
                mutable_patch = await session.get(type(patch), patch.id)
                mutation = await session.get(MutationModel, mutation_id)
                mutable_patch.review_digest = PatchService._review_digest(mutable_patch.base_commit_sha, [mutation])
                await session.commit()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://lens.test") as client:
                response = await client.get(path, headers=headers)
                assert response.status_code == 200, response.text
                assert response.json()["review"]["current"] is False
                assert response.json()["review"]["approved"] is False
        finally:
            app.dependency_overrides.pop(get_session, None)

        async with engine.begin() as conn:
            await conn.execute(text("GRANT SELECT ON context_change_sets TO forge_rls_test"))
        async with engine.connect() as conn:
            with pytest.raises(Exception, match="append-only"):
                await conn.execute(text("UPDATE context_change_sets SET schema_version = 2 WHERE id = :id"),
                                   {"id": change.id})
            await conn.rollback()
        async with engine.connect() as conn:
            await conn.execute(text("SET ROLE forge_rls_test"))
            await conn.execute(text("SELECT set_config('forge.organization_id', :org, false)"), {"org": str(other)})
            assert (await conn.execute(text("SELECT count(*) FROM context_change_sets WHERE id = :id"),
                                       {"id": change.id})).scalar_one() == 0
            await conn.rollback()
    finally:
        await engine.dispose()
