import os
from datetime import UTC, datetime, timedelta
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.main import app
from packages.database.engine import get_session
from packages.database.models.atlas import AtlasJobModel, AtlasNodeModel, AtlasSnapshotModel
from packages.database.models.auth import OrganizationModel, RoleBindingModel, SessionModel, UserModel
from packages.database.models.execution import ExecutionJobModel, ExecutionStatus, MutationModel
from packages.database.models.planning import PlanModel, PlanStatus, TaskNodeModel
from packages.database.models.repository import RepositoryModel, RepositoryStatus
from packages.database.models.verification import VerificationJobModel, VerificationResultModel, VerificationStatus
from packages.database.models.verification_intelligence import VerificationPlanModel
from packages.database.tenant import set_system_context
from services.auth.jwt import create_access_token
from services.execution.sandbox import SandboxResult
from services.execution.workspace import execution_workspace_path
from services.verification.service import VerificationDispatcher


@pytest.mark.asyncio
@pytest.mark.parametrize("stale", [False, True])
async def test_persisted_selection_is_scoped_immutable_and_worker_fails_closed(tmp_path, stale):
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Disposable migrated PostgreSQL required")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    org, other, user_id, repo_id, plan_id, execution_id, task_id, mutation_id, browser_id = (uuid4() for _ in range(9))
    token_secret = str(uuid4())
    settings = SimpleNamespace(workspace_root=str(tmp_path), sandbox_images=("python:3.12",))
    workspace = execution_workspace_path(str(tmp_path), org, repo_id, execution_id, 0)
    workspace.mkdir(parents=True)
    (workspace / "forge.yaml").write_text("""version: 1
languages: [python]
verification:
  test:
    - {identifier: focused, display_name: Focused, category: test, command: [pytest, tests/test_a.py]}
    - {identifier: unrelated, display_name: Unrelated, category: test, command: [pytest, tests/test_b.py]}
""")
    set_system_context()
    try:
        async with sessions() as session:
            session.add_all([
                OrganizationModel(id=org, name=f"vi-{org}"),
                OrganizationModel(id=other, name=f"vi-{other}"),
                UserModel(id=user_id, name="VI", email=f"vi-{user_id}@example.invalid"),
                RepositoryModel(id=repo_id, organization_id=org, owner="vi", name="fixture",
                                full_name="vi/fixture", clone_url="https://github.com/vi/fixture.git",
                                status=RepositoryStatus.READY, commit_sha="a" * 40),
            ])
            await session.flush()
            session.add_all([
                RoleBindingModel(id=uuid4(), organization_id=org, user_id=user_id, role="OWNER"),
                RoleBindingModel(id=uuid4(), organization_id=other, user_id=user_id, role="OWNER"),
                SessionModel(id=browser_id, user_id=user_id, session_token=token_secret,
                             expires_at=(datetime.now(UTC) + timedelta(hours=1)).replace(tzinfo=None)),
                PlanModel(id=plan_id, organization_id=org, repository_id=repo_id, status=PlanStatus.APPROVED,
                          intent="Edit test", context_snapshot={}),
            ])
            await session.flush()
            session.add(ExecutionJobModel(id=execution_id, organization_id=org, repository_id=repo_id,
                                          plan_id=plan_id, status=ExecutionStatus.COMPLETED,
                                          commit_sha_before="a" * 40, lease_generation=0))
            await session.flush()
            session.add(TaskNodeModel(id=task_id, organization_id=org, plan_id=plan_id,
                                      action_type="edit_file", target="tests/test_a.py", parameters={}))
            await session.flush()
            session.add(MutationModel(id=mutation_id, organization_id=org, repository_id=repo_id,
                                      execution_job_id=execution_id, task_node_id=task_id,
                                      file_path="tests/test_a.py", mutation_type="UPDATE",
                                      diff_hunk="--- tests/test_a.py\n+++ tests/test_a.py\n@@ -1 +1 @@\n-old\n+new\n"))
            atlas_job_id, snapshot_id, node_id = uuid4(), uuid4(), uuid4()
            session.add(AtlasJobModel(id=atlas_job_id, organization_id=org, repository_id=repo_id,
                                      requested_by=user_id, idempotency_key=uuid4(), status="SUCCEEDED", attempts=1))
            await session.flush()
            session.add(AtlasSnapshotModel(id=snapshot_id, organization_id=org, repository_id=repo_id,
                                           job_id=atlas_job_id, commit_sha="a" * 40, tree_sha="b" * 40,
                                           source_fingerprint="c" * 64, dirty=False, indexer_version="atlas-5",
                                           parser_versions={}, config_fingerprint="d" * 64, status="BUILDING",
                                           stats={}, warnings=[], completed_at=datetime.now(UTC)))
            await session.flush()
            session.add(AtlasNodeModel(id=node_id, organization_id=org, repository_id=repo_id,
                                       snapshot_id=snapshot_id, stable_key="file:tests/test_a.py",
                                       kind="test_file", name="tests/test_a.py", path="tests/test_a.py"))
            await session.flush()
            snapshot = await session.get(AtlasSnapshotModel, snapshot_id)
            snapshot.status = "PUBLISHED"
            await session.commit()

        async with sessions() as session:
            dispatcher = VerificationDispatcher(session, org, settings)
            job = await dispatcher.trigger_verification(execution_id)
            assert (await dispatcher.trigger_verification(execution_id)).id == job.id
            selection = (await session.execute(select(VerificationPlanModel).where(
                VerificationPlanModel.verification_job_id == job.id))).scalar_one()
            assert selection.change_set_id and selection.patch_digest
            assert selection.decision["selected_verifiers"] == ["focused"]
            assert selection.decision["verifier_targets"]["focused"] == "tests/test_a.py"
            assert selection.decision["deferred_verifiers"] == [
                {"id": "unrelated", "reason": "UNRELATED_EXPLICIT_TEST"}]
            assert selection.decision["snapshot_id"] == str(snapshot_id)

        async def api_session():
            async with sessions() as session:
                yield session

        app.dependency_overrides[get_session] = api_session
        try:
            jwt = create_access_token({"sub": str(user_id), "session_id": str(browser_id),
                                       "session_token": token_secret})
            route = f"/api/v1/verifications/executions/{execution_id}/intelligence"
            headers = {"Authorization": f"Bearer {jwt}", "X-Organization-Id": str(org)}
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://vi.test") as client:
                started = perf_counter()
                response = await client.get(route, headers=headers)
                print(f"Verification Intelligence fixture read: {(perf_counter() - started) * 1000:.1f} ms, {len(response.content)} bytes")
                assert response.status_code == 200, response.text
                assert len(response.content) < 100_000
                assert response.json()["plan"]["current"] is True
                assert response.json()["plan"]["selected_verifiers"] == ["focused"]
                assert response.json()["results"] == []
                assert response.json()["coverage_claimed"] is False
                preview = await client.get(route + "/preview", headers=headers)
                assert preview.status_code == 200 and not preview.json()["configuration_checked"]
                assert (await client.get(route, headers={**headers, "X-Organization-Id": str(other)})).status_code == 404
                assert (await client.get(route.replace(str(execution_id), str(uuid4())), headers=headers)).status_code == 404
        finally:
            app.dependency_overrides.pop(get_session, None)

        if stale:
            async with sessions() as session:
                mutation = await session.get(MutationModel, mutation_id)
                mutation.diff_hunk = mutation.diff_hunk.replace("+new", "+changed")
                await session.commit()
            app.dependency_overrides[get_session] = api_session
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://vi.test") as client:
                    response = await client.get(route, headers=headers)
                    assert response.status_code == 200 and response.json()["plan"]["current"] is False
            finally:
                app.dependency_overrides.pop(get_session, None)
        sandbox = AsyncMock()
        sandbox.run_command.return_value = SandboxResult(exit_code=0, stdout="ok", stderr="")
        with patch("services.verification.service.DockerSandbox", return_value=sandbox):
            async with sessions() as session:
                await VerificationDispatcher(session, org, settings).run_verification(job.id)
        async with sessions() as session:
            completed = await session.get(VerificationJobModel, job.id)
            results = (await session.execute(select(VerificationResultModel).where(
                VerificationResultModel.verification_job_id == job.id))).scalars().all()
            assert completed.status == (VerificationStatus.BLOCKED if stale else VerificationStatus.PASSED)
            assert sorted(item.status.value for item in results) == ([] if stale else ["PASSED", "SKIPPED"])
            assert sandbox.run_command.await_count == (0 if stale else 1)
            assert (await session.execute(select(VerificationPlanModel).where(
                VerificationPlanModel.verification_job_id == job.id))).scalar_one().decision["selected_verifiers"] == ["focused"]
        async with engine.begin() as conn:
            await conn.execute(text("GRANT SELECT ON verification_plans TO forge_rls_test"))
        async with engine.connect() as conn:
            with pytest.raises(Exception, match="append-only"):
                await conn.execute(text("UPDATE verification_plans SET schema_version = 2 WHERE id = :id"),
                                   {"id": selection.id})
            await conn.rollback()
        async with engine.connect() as conn:
            await conn.execute(text("SET ROLE forge_rls_test"))
            await conn.execute(text("SELECT set_config('forge.organization_id', :org, false)"), {"org": str(other)})
            assert (await conn.execute(text("SELECT count(*) FROM verification_plans WHERE id = :id"),
                                       {"id": selection.id})).scalar_one() == 0
            await conn.rollback()
    finally:
        await engine.dispose()
