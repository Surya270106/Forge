"""Local PostgreSQL workflow check; GitHub reads are mocked and no model is called."""

import os
from unittest.mock import AsyncMock
from unittest.mock import patch as mock_patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database.models.planning import PlanModel, PlanStatus
from services.issue_to_pr.api import CaptureIssueRequest, capture_issue, get_workflow, plan_issue


@pytest.mark.asyncio
async def test_capture_is_durable_idempotent_and_tenant_scoped():
    url = os.getenv("FORGE_ISSUE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set FORGE_ISSUE_TEST_DATABASE_URL for disposable local PostgreSQL")
    if os.getenv("FORGE_ISSUE_TEST_CONFIRM_DISPOSABLE") != "1":
        pytest.skip("Confirm this database is disposable before running issue workflow persistence")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    org, repo, user_id = uuid4(), uuid4(), uuid4()
    user = {"id": str(user_id)}
    issue_id = uuid4().int % 1_000_000_000 + 30
    key = uuid4()
    issue = {"github_repository_id": 17, "github_issue_id": issue_id, "number": issue_id,
             "title": "Local fixture", "body": "Untrusted issue data", "labels": [], "state": "open",
             "url": f"https://github.com/owner/repo/issues/{issue_id}", "repository": "owner/repo",
             "base_branch": "main", "base_commit_sha": "a" * 40, "captured_at": "2026-11-14T00:00:00Z"}
    planned_id = None
    async with engine.begin() as conn:
        await conn.execute(text("INSERT INTO organizations (id,name,billing_plan,is_active) VALUES (:id,:name,'FREE',true)"),
                           {"id": org, "name": f"issue-test-{org}"})
        await conn.execute(text("INSERT INTO users (id,email,name,is_active) VALUES (:id,:email,'Issue Test',true)"),
                           {"id": user_id, "email": f"{user_id}@example.invalid"})
        await conn.execute(text("""INSERT INTO repositories
            (id,organization_id,owner,name,full_name,clone_url,default_branch,status,commit_sha,total_files,total_size_bytes,is_private)
            VALUES (:id,:org,'owner',:name,'owner/repo','https://github.com/owner/repo.git','main','READY',:sha,0,0,false)"""),
                           {"id": repo, "org": org, "name": f"repo-{repo}", "sha": "a" * 40})
    try:
        with (mock_patch("services.issue_to_pr.api._issue_client", new=AsyncMock(return_value=({"id": 17}, issue))),
              mock_patch("services.issue_to_pr.api.require_github_token", new=AsyncMock(return_value="fixture-token"))):
            async with sessions() as session:
                await session.execute(text("SELECT set_config('forge.organization_id', :org, true)"), {"org": str(org)})
                first = await capture_issue(repo, CaptureIssueRequest(issue_number=issue_id, idempotency_key=key), org, user, session)
            async with sessions() as session:
                await session.execute(text("SELECT set_config('forge.organization_id', :org, true)"), {"org": str(org)})
                duplicate = await capture_issue(repo, CaptureIssueRequest(issue_number=issue_id, idempotency_key=key), org, user, session)
                assert duplicate["id"] == first["id"]
                assert duplicate["state"] == "ISSUE_CAPTURED"
            async with sessions() as session:
                await session.execute(text("SELECT set_config('forge.organization_id', :org, true)"), {"org": str(org)})
                restored = await get_workflow(UUID(first["id"]), org, session)
                assert restored["issue"]["github_issue_id"] == issue_id
                assert restored["atlas_snapshot_id"] is None
                with pytest.raises(HTTPException) as forbidden:
                    await get_workflow(UUID(first["id"]), uuid4(), session)
                assert forbidden.value.status_code == 404

            async def fixture_plan(service, repository_id, intent, *, plan_id):
                assert repository_id == repo
                assert "Atlas graph is unavailable" in intent
                plan = PlanModel(id=plan_id, organization_id=org, repository_id=repo,
                                 status=PlanStatus.PENDING_APPROVAL, intent=intent, context_snapshot={})
                service.session.add(plan)
                await service.session.commit()
                return plan

            with mock_patch("services.issue_to_pr.api.PlanningService.create_plan", new=fixture_plan):
                async with sessions() as session:
                    await session.execute(text("SELECT set_config('forge.organization_id', :org, true)"), {"org": str(org)})
                    planned = await plan_issue(UUID(first["id"]), org, session)
                    planned_id = planned["plan_id"]
                    assert planned["state"] == "AWAITING_EXECUTION_AUTHORIZATION"
                    assert planned["atlas_snapshot_id"] is None
                    assert planned["candidate_paths"] == []
                async with sessions() as session:
                    await session.execute(text("SELECT set_config('forge.organization_id', :org, true)"), {"org": str(org)})
                    restored = await get_workflow(UUID(first["id"]), org, session)
                    assert restored["plan_id"] == planned_id
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM issue_workflows WHERE organization_id=:org"), {"org": org})
            if planned_id:
                await conn.execute(text("DELETE FROM plans WHERE id=:plan"), {"plan": UUID(planned_id)})
            await conn.execute(text("DELETE FROM repositories WHERE id=:repo"), {"repo": repo})
            await conn.execute(text("DELETE FROM organizations WHERE id=:org"), {"org": org})
            await conn.execute(text("DELETE FROM users WHERE id=:user"), {"user": user_id})
        await engine.dispose()
