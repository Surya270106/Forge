"""Immutable, tenant-scoped Context Lens change-set evidence.

Revision ID: e1b4c8d29070
Revises: d6a1f8b2c340
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "e1b4c8d29070"
down_revision = "d6a1f8b2c340"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "context_change_sets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("repository_id", sa.Uuid(), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("execution_job_id", sa.Uuid(), sa.ForeignKey("execution_jobs.id"), nullable=False),
        sa.Column("patch_id", sa.Uuid(), sa.ForeignKey("patches.id"), nullable=False),
        sa.Column("base_snapshot_id", sa.Uuid()),
        sa.Column("base_commit_sha", sa.String(40), nullable=False),
        sa.Column("review_digest", sa.String(64), nullable=False),
        sa.Column("file_changes", JSONB(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("patch_id", name="uq_context_change_set_patch"),
        sa.ForeignKeyConstraint(["base_snapshot_id", "organization_id", "repository_id"],
                                ["atlas_snapshots.id", "atlas_snapshots.organization_id", "atlas_snapshots.repository_id"],
                                name="fk_context_base_snapshot_scope"),
    )
    op.create_index("ix_context_change_sets_execution", "context_change_sets", ["organization_id", "execution_job_id"])
    op.execute("ALTER TABLE context_change_sets ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE context_change_sets FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY context_change_sets_tenant_policy ON context_change_sets
        USING (current_user = 'forge_admin' OR organization_id::text = current_setting('forge.organization_id', true))
        WITH CHECK (current_user = 'forge_admin' OR organization_id::text = current_setting('forge.organization_id', true))""")
    op.execute("""CREATE TRIGGER context_change_sets_append_only BEFORE UPDATE OR DELETE ON context_change_sets
        FOR EACH ROW EXECUTE FUNCTION forbid_execution_event_mutation()""")


def downgrade() -> None:
    op.drop_table("context_change_sets")
