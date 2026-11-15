import os
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.database.models.auth import OrganizationModel, UserModel
from packages.database.models.safety import SafetyPolicyModel
from packages.database.tenant import set_system_context
from services.safety.policy import decide
from services.safety.service import as_document, current_policy, from_document, revise_policy


@pytest.mark.asyncio
async def test_versioned_policy_revocation_history_and_rls():
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Disposable migrated PostgreSQL database required")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    organization_id, other_id, user_id, repo_id = (uuid4() for _ in range(4))
    set_system_context()
    try:
        async with sessions() as session:
            session.add_all([OrganizationModel(id=organization_id, name=f"safety-{organization_id}"),
                             OrganizationModel(id=other_id, name=f"safety-{other_id}"),
                             UserModel(id=user_id, name="Safety", email=f"safety-{user_id}@example.invalid")])
            await session.commit()
        async with sessions() as session:
            initial = await current_policy(session, organization_id)
            assert initial.version == 0
            first = await revise_policy(session, organization_id, user_id,
                                        repository_denies={str(repo_id): ["repository:write"]})
            await session.commit()
            assert first.version == 1
            snapshot = from_document(as_document(first))
        async with sessions() as session:
            stopped = await revise_policy(session, organization_id, user_id, stopped=True)
            await session.commit()
            assert stopped.version == 2
            assert decide("edit_file", "main.py", snapshot, stopped, repository_id=repo_id).effect == "DENY"
            assert decide("command", "pytest -q", snapshot, stopped, repository_id=repo_id).effect == "DENY"
            row = (await session.execute(select(SafetyPolicyModel).where(
                SafetyPolicyModel.organization_id == organization_id,
            ).order_by(SafetyPolicyModel.version))).scalars().first()
            assert row is not None
            row.denied = ["command:execute"]
            with pytest.raises(DBAPIError):
                await session.commit()
            await session.rollback()
        async with engine.begin() as connection:
            await connection.execute(text("""DO $$ BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'forge_safety_rls_test') THEN
                    CREATE ROLE forge_safety_rls_test NOLOGIN NOSUPERUSER NOBYPASSRLS;
                END IF;
            END $$"""))
            await connection.execute(text("GRANT USAGE ON SCHEMA public TO forge_safety_rls_test"))
            await connection.execute(text("GRANT SELECT ON safety_policies TO forge_safety_rls_test"))
            await connection.execute(text("SET LOCAL ROLE forge_safety_rls_test"))
            await connection.execute(text("SELECT set_config('forge.organization_id', :org, true)"), {"org": str(other_id)})
            assert (await connection.execute(text("SELECT id FROM safety_policies WHERE organization_id=:org"),
                                             {"org": organization_id})).all() == []
    finally:
        await engine.dispose()
