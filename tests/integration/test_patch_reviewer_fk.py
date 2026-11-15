"""The migrated schema must preserve patch reviewer references."""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_patch_reviewer_foreign_key_is_present_and_restricts_deletion():
    url = os.environ.get("FORGE_RLS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Disposable migrated PostgreSQL database required")
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            rows = (await connection.execute(text("""
                SELECT constraint_row.confdeltype FROM pg_constraint AS constraint_row
                JOIN pg_attribute AS column_row ON column_row.attrelid = constraint_row.conrelid
                    AND column_row.attname = 'reviewed_by'
                WHERE constraint_row.conrelid = 'patches'::regclass
                    AND constraint_row.confrelid = 'users'::regclass
                    AND constraint_row.conkey = ARRAY[column_row.attnum]::smallint[]
            """))).all()
            assert rows == [(b"a",)]
    finally:
        await engine.dispose()
