"""Immutable, tenant-scoped verification decisions.

Revision ID: f2c7d4e9a110
Revises: e1b4c8d29070
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "f2c7d4e9a110"
down_revision = "e1b4c8d29070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_context_change_set_scope", "context_change_sets",
                                ["id", "organization_id", "repository_id"])
    op.create_table(
        "verification_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("repository_id", sa.Uuid(), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("execution_job_id", sa.Uuid(), sa.ForeignKey("execution_jobs.id"), nullable=False),
        sa.Column("verification_job_id", sa.Uuid(), sa.ForeignKey("verification_jobs.id"), nullable=False),
        sa.Column("change_set_id", sa.Uuid(), nullable=False),
        sa.Column("base_commit_sha", sa.String(40), nullable=False),
        sa.Column("patch_digest", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("decision", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("verification_job_id", name="uq_verification_plan_job"),
        sa.ForeignKeyConstraint(["change_set_id", "organization_id", "repository_id"],
                                ["context_change_sets.id", "context_change_sets.organization_id",
                                 "context_change_sets.repository_id"], name="fk_verification_plan_change_scope"),
    )
    op.execute("ALTER TABLE verification_plans ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE verification_plans FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY verification_plans_tenant_policy ON verification_plans
        USING (current_user = 'forge_admin' OR organization_id::text = current_setting('forge.organization_id', true))
        WITH CHECK (current_user = 'forge_admin' OR organization_id::text = current_setting('forge.organization_id', true))""")
    op.execute("""CREATE TRIGGER verification_plans_append_only BEFORE UPDATE OR DELETE ON verification_plans
        FOR EACH ROW EXECUTE FUNCTION forbid_execution_event_mutation()""")


def downgrade() -> None:
    op.drop_table("verification_plans")
    op.drop_constraint("uq_context_change_set_scope", "context_change_sets", type_="unique")
