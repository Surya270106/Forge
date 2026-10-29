"""Exercise PostgreSQL policies as a real role without RLS bypass privileges."""

import os
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from services.auth import api as auth_api
from services.auth.jwt import decode_access_token


@pytest.mark.asyncio
async def test_repository_rls_isolates_tenants():
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    if not url:
        if os.environ.get("CI") or os.environ.get("FORGE_REQUIRE_RLS_TEST"):
            pytest.fail("FORGE_RLS_TEST_DATABASE_URL is required for the CI RLS gate")
        pytest.skip("Set FORGE_RLS_TEST_DATABASE_URL to an isolated migrated PostgreSQL database")
    engine = create_async_engine(url)
    first, second = uuid4(), uuid4()
    first_repo, second_repo = uuid4(), uuid4()
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("""
                DO $$ BEGIN
                    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'forge_rls_test') THEN
                        CREATE ROLE forge_rls_test NOLOGIN NOSUPERUSER NOBYPASSRLS;
                    END IF;
                END $$
            """)
            )
            await conn.execute(text("GRANT USAGE ON SCHEMA public TO forge_rls_test"))
            await conn.execute(text("GRANT SELECT ON repositories TO forge_rls_test"))
            for org, repo in ((first, first_repo), (second, second_repo)):
                await conn.execute(
                    text("""
                    INSERT INTO repositories
                    (id, organization_id, owner, name, full_name, clone_url,
                     default_branch, status, total_files, total_size_bytes, is_private)
                    VALUES (:repo, :org, 'forge-rls-test', :name, :full_name,
                            'https://example.invalid/repo.git', 'main', 'READY', 0, 0, false)
                """),
                    {"repo": repo, "org": org, "name": str(repo), "full_name": f"forge-rls-test/{repo}"},
                )
            await conn.execute(text("SET LOCAL ROLE forge_rls_test"))
            role = (await conn.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"))).one()
            assert role == (False, False)
            query = text("SELECT id FROM repositories WHERE id IN (:first, :second)")
            params = {"first": first_repo, "second": second_repo}
            assert (await conn.execute(query, params)).scalars().all() == []
            await conn.execute(text("SELECT set_config('forge.organization_id', :org, true)"), {"org": str(first)})
            assert (await conn.execute(query, params)).scalars().all() == [first_repo]
            await conn.execute(text("SELECT set_config('forge.organization_id', :org, true)"), {"org": str(second)})
            assert (await conn.execute(query, params)).scalars().all() == [second_repo]
            await conn.execute(text("RESET ROLE"))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_oauth_onboarding_and_workspace_discovery_with_restricted_role(monkeypatch):
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    if not url:
        if os.environ.get("CI") or os.environ.get("FORGE_REQUIRE_RLS_TEST"):
            pytest.fail("FORGE_RLS_TEST_DATABASE_URL is required")
        pytest.skip("Set FORGE_RLS_TEST_DATABASE_URL to an isolated migrated PostgreSQL database")
    engine = create_async_engine(url)
    state = f"oauth-{uuid4()}"
    other_org, other_user, other_session = uuid4(), uuid4(), f"other-{uuid4()}"
    email = f"{uuid4()}@example.invalid"
    other_email = f"{uuid4()}@example.invalid"
    captured = []

    class FakeRedis:
        async def set(self, _key, value, **_kwargs):
            captured.append(json.loads(value))
            return True

        async def aclose(self):
            pass

    class FakeResponse:
        status_code = 200

        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

    class FakeGitHub:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def post(self, *_args, **_kwargs):
            return FakeResponse({"access_token": "ghp_testing_only_12345678"})

        async def get(self, url, **_kwargs):
            if url == auth_api.GITHUB_USER_URL:
                return FakeResponse({"name": "RLS Test", "login": "rls-test"})
            return FakeResponse([{"email": email, "primary": True}])

    monkeypatch.setattr(auth_api.httpx, "AsyncClient", FakeGitHub)
    monkeypatch.setattr(auth_api.redis_async, "from_url", lambda _url: FakeRedis())
    monkeypatch.setattr(auth_api, "get_settings", lambda: SimpleNamespace(
        github_client_id="test-id", github_client_secret=SimpleNamespace(get_secret_value=lambda: "test-secret"),
        redis_url="redis://unused", frontend_url="https://example.invalid",
    ))
    request = Request({"type": "http", "method": "GET", "path": "/callback", "headers": []})
    try:
        async with engine.begin() as conn:
            await conn.execute(text("""DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'forge_rls_test') THEN
                    CREATE ROLE forge_rls_test NOLOGIN NOSUPERUSER NOBYPASSRLS;
                END IF;
            END $$"""))
            await conn.execute(text("GRANT USAGE ON SCHEMA public TO forge_rls_test"))
            await conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON users, organizations, role_bindings, sessions, oauth_states TO forge_rls_test"))
            await conn.execute(text("INSERT INTO oauth_states (id,state,expires_at,created_at,updated_at) VALUES (:id,:state,:expires,now(),now())"),
                               {"id": uuid4(), "state": state, "expires": datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=10)})
            await conn.execute(text("INSERT INTO organizations (id,name,billing_plan,is_active,created_at,updated_at) VALUES (:id,:name,'FREE',true,now(),now())"),
                               {"id": other_org, "name": f"Other {other_org}"})
            await conn.execute(text("INSERT INTO users (id,email,name,is_active,created_at,updated_at) VALUES (:id,:email,'Other',true,now(),now())"),
                               {"id": other_user, "email": other_email})
            await conn.execute(text("INSERT INTO role_bindings (id,organization_id,user_id,role,created_at,updated_at) VALUES (:id,:org,:user,'OWNER',now(),now())"),
                               {"id": uuid4(), "org": other_org, "user": other_user})
            await conn.execute(text("INSERT INTO sessions (id,user_id,session_token,expires_at,is_active,created_at,updated_at) VALUES (:id,:user,:token,:expires,true,now(),now())"),
                               {"id": uuid4(), "user": other_user, "token": other_session, "expires": datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)})

        async with engine.connect() as conn:
            await conn.execute(text("SET ROLE forge_rls_test"))
            await conn.commit()
            sessions = async_sessionmaker(bind=conn, expire_on_commit=False)
            async with sessions() as session:
                role = (await session.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user"))).one()
                assert role == (False, False)
                response = await auth_api.github_callback("mocked-code", state, request, session)
                assert response.status_code == 307
                token = captured[-1]["token"]
                claims = decode_access_token(token)
                assert claims is not None
                own = await auth_api.get_workspaces({"session_token": claims["session_token"]}, session)
                assert len(own["workspaces"]) == 1
                assert own["workspaces"][0]["id"] == captured[-1]["org_id"]
                assert own["workspaces"][0]["id"] != str(other_org)
                await session.commit()

                # A valid session for another user cannot discover the new user's workspace.
                other = await auth_api.get_workspaces({"session_token": other_session}, session)
                assert [workspace["id"] for workspace in other["workspaces"]] == [str(other_org)]
                await session.commit()

                # A second OAuth login reuses the same binding and default workspace.
                await conn.execute(text("RESET ROLE"))
                await conn.execute(text("INSERT INTO oauth_states (id,state,expires_at,created_at,updated_at) VALUES (:id,:state,:expires,now(),now())"),
                                   {"id": uuid4(), "state": f"{state}-again", "expires": datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=10)})
                await conn.commit()
                await conn.execute(text("SET ROLE forge_rls_test"))
                await conn.commit()
                await auth_api.github_callback("mocked-code", f"{state}-again", request, session)
                assert captured[-1]["org_id"] == captured[0]["org_id"]
                latest_claims = decode_access_token(captured[-1]["token"])
                assert latest_claims is not None
                assert len((await auth_api.get_workspaces({"session_token": latest_claims["session_token"]}, session))["workspaces"]) == 1
                await session.commit()
            await conn.execute(text("RESET ROLE"))
            await conn.commit()
    finally:
        await engine.dispose()
