"""add tenant rls policies

Revision ID: d7b5578b4249
Revises: 56af2791774f
Create Date: 2026-07-20 11:10:08.544267

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7b5578b4249"
down_revision: str | None = "56af2791774f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


tenant_tables = [
    "role_bindings",
    "context_snapshots",
    "agent_interactions",
    "execution_jobs",
    "mutations",
    "import_jobs",
    "repository_memory_versions",
    "source_files",
    "symbols",
    "symbol_references",
    "dependency_edges",
    "call_edges",
    "ast_cache_entries",
    "indexing_jobs",
    "plans",
    "task_nodes",
    "task_edges",
    "repositories",
    "repository_manifests",
    "verification_jobs",
    "repair_attempts",
]


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'forge_admin') THEN CREATE ROLE forge_admin; END IF; END $$;"
    )

    for table in tenant_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(f"""
        CREATE POLICY {table}_tenant_policy ON {table}
        AS PERMISSIVE FOR ALL
        TO PUBLIC
        USING (
            current_user = 'forge_admin' 
            OR organization_id::text = current_setting('forge.organization_id', true)
        )
        WITH CHECK (
            current_user = 'forge_admin' 
            OR organization_id::text = current_setting('forge.organization_id', true)
        );
        """)


def downgrade() -> None:
    for table in tenant_tables:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_policy ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
