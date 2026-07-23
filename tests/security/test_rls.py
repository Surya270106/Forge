import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://forge:forge@localhost:5432/forge")


@pytest.mark.asyncio
async def test_forge_user_has_no_rls_bypass():
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.begin() as conn:
            # Check if the current user has superuser or bypassrls privileges
            result = await conn.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"))
            row = result.fetchone()
            assert row is not None, "Could not fetch role information"

            # These must both be False for RLS to be enforced properly
            is_super = row[0]
            can_bypass_rls = row[1]

            assert is_super is False, "Forge application user must NOT be a superuser"
            assert can_bypass_rls is False, "Forge application user must NOT have BYPASSRLS privilege"
    finally:
        await engine.dispose()
