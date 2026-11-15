"""Bind issue work to stable GitHub identity and existing engineering records.

Revision ID: b6f1a2c3d4e5
Revises: a4d1e8c2b930
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "b6f1a2c3d4e5"
down_revision = "a4d1e8c2b930"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("repositories", sa.Column("github_repository_id", sa.BigInteger(), nullable=True))
    op.create_index("ix_repositories_github_id", "repositories", ["organization_id", "github_repository_id"], unique=True)
    op.create_table(
        "issue_workflows",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("repository_id", sa.Uuid(), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("github_repository_id", sa.BigInteger(), nullable=False),
        sa.Column("github_issue_id", sa.BigInteger(), nullable=False),
        sa.Column("issue_number", sa.Integer(), nullable=False),
        sa.Column("issue_snapshot", JSONB(), nullable=False),
        sa.Column("base_commit_sha", sa.String(40), nullable=False),
        sa.Column("atlas_snapshot_id", sa.Uuid(), sa.ForeignKey("atlas_snapshots.id"), nullable=True),
        sa.Column("candidate_paths", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("pending_plan_id", sa.Uuid(), nullable=True),
        sa.Column("plan_id", sa.Uuid(), sa.ForeignKey("plans.id"), nullable=True),
        sa.Column("last_error", sa.String(80), nullable=True),
        sa.Column("planned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "repository_id", "idempotency_key", name="uq_issue_workflow_request"),
        sa.UniqueConstraint("organization_id", "github_repository_id", "github_issue_id", "base_commit_sha", name="uq_issue_workflow_source"),
        sa.UniqueConstraint("plan_id", name="uq_issue_workflow_plan"),
        sa.CheckConstraint("issue_number > 0 AND github_issue_id > 0 AND github_repository_id > 0", name="ck_issue_workflow_provider_ids"),
        sa.CheckConstraint("base_commit_sha ~ '^[0-9a-f]{40}$'", name="ck_issue_workflow_base_sha"),
    )
    op.create_index("ix_issue_workflow_repo", "issue_workflows", ["organization_id", "repository_id", "created_at"])
    op.create_index("ix_issue_workflow_issue", "issue_workflows", ["github_repository_id", "github_issue_id"])
    op.execute("ALTER TABLE issue_workflows ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE issue_workflows FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY issue_workflows_tenant_policy ON issue_workflows
        USING (current_user = 'forge_admin' OR organization_id::text = current_setting('forge.organization_id', true))
        WITH CHECK (current_user = 'forge_admin' OR organization_id::text = current_setting('forge.organization_id', true))""")
    op.execute("""CREATE FUNCTION forbid_issue_workflow_source_change() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
                OR NEW.repository_id IS DISTINCT FROM OLD.repository_id
                OR NEW.created_by IS DISTINCT FROM OLD.created_by
                OR NEW.github_repository_id IS DISTINCT FROM OLD.github_repository_id
                OR NEW.github_issue_id IS DISTINCT FROM OLD.github_issue_id
                OR NEW.issue_number IS DISTINCT FROM OLD.issue_number
                OR NEW.issue_snapshot IS DISTINCT FROM OLD.issue_snapshot
                OR NEW.base_commit_sha IS DISTINCT FROM OLD.base_commit_sha THEN
                RAISE EXCEPTION 'Issue workflow source is immutable';
            END IF;
            RETURN NEW;
        END $$""")
    op.execute("""CREATE TRIGGER issue_workflow_source_immutable BEFORE UPDATE ON issue_workflows
        FOR EACH ROW EXECUTE FUNCTION forbid_issue_workflow_source_change()""")


def downgrade() -> None:
    op.drop_table("issue_workflows")
    op.execute("DROP FUNCTION forbid_issue_workflow_source_change()")
    op.drop_index("ix_repositories_github_id", table_name="repositories")
    op.drop_column("repositories", "github_repository_id")
