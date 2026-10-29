"""Pin patch review and track GitHub contribution state.

Revision ID: f74a1d2e3c60
Revises: 45529f0ecf3d
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f74a1d2e3c60"
down_revision = "45529f0ecf3d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Older installations may already have applied c171ce8c8213, whose
    # original upgrade dropped patches. Restore the table only when absent;
    # existing patch rows and indexes must never be replaced here.
    if not sa.inspect(op.get_bind()).has_table("patches"):
        op.create_table(
            "patches",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("organization_id", sa.Uuid(), nullable=False),
            sa.Column("repository_id", sa.Uuid(), sa.ForeignKey("repositories.id"), nullable=False),
            sa.Column("execution_job_id", sa.Uuid(), sa.ForeignKey("execution_jobs.id"), nullable=False),
            sa.Column("task_id", sa.Uuid(), sa.ForeignKey("task_nodes.id"), nullable=True),
            sa.Column("status", postgresql.ENUM(name="patch_status", create_type=False), nullable=False),
            sa.Column("total_additions", sa.Integer(), server_default="0", nullable=False),
            sa.Column("total_deletions", sa.Integer(), server_default="0", nullable=False),
            sa.Column("files_changed", sa.Integer(), server_default="0", nullable=False),
            sa.Column("pull_request_url", sa.String(500), nullable=True),
            sa.Column("pull_request_number", sa.Integer(), nullable=True),
            sa.Column("branch_name", sa.String(255), nullable=True),
            sa.Column("commit_sha", sa.String(40), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reviewed_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        )
        op.create_index("ix_patches_exec", "patches", ["execution_job_id"])
        op.create_index("ix_patches_repo_org", "patches", ["repository_id", "organization_id"])
        op.create_index("ix_patches_status", "patches", ["status"])
    op.execute("ALTER TYPE repair_attempt_status ADD VALUE IF NOT EXISTS 'AWAITING_APPROVAL'")
    op.add_column("repair_attempts", sa.Column("repair_plan_id", sa.Uuid(), nullable=True))
    op.add_column("repair_attempts", sa.Column("requested_by", sa.Uuid(), nullable=True))
    op.add_column("repair_attempts", sa.Column("error_message", sa.String(255), nullable=True))
    op.create_foreign_key("fk_repair_attempts_plan", "repair_attempts", "plans", ["repair_plan_id"], ["id"])
    op.create_foreign_key("fk_repair_attempts_requested_by", "repair_attempts", "users", ["requested_by"], ["id"])
    op.create_unique_constraint("uq_repair_attempts_plan", "repair_attempts", ["repair_plan_id"])
    op.drop_index("ix_repositories_owner_name", table_name="repositories")
    op.create_index("ix_repositories_owner_name", "repositories", ["organization_id", "owner", "name"], unique=True)
    op.add_column("patches", sa.Column("base_commit_sha", sa.String(40), nullable=True))
    op.add_column("patches", sa.Column("branch_url", sa.String(500), nullable=True))
    op.add_column("patches", sa.Column("review_digest", sa.String(64), nullable=True))
    op.add_column("patches", sa.Column("publish_status", sa.String(20), server_default="NOT_REQUESTED", nullable=False))
    op.add_column("patches", sa.Column("publish_error", sa.String(255), nullable=True))
    op.execute("ALTER TABLE patches ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE patches FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY patches_tenant_policy ON patches FOR ALL TO PUBLIC
        USING (current_user = 'forge_admin' OR organization_id::text = current_setting('forge.organization_id', true))
        WITH CHECK (current_user = 'forge_admin' OR organization_id::text = current_setting('forge.organization_id', true))
    """)


def downgrade() -> None:
    op.drop_constraint("uq_repair_attempts_plan", "repair_attempts", type_="unique")
    op.drop_constraint("fk_repair_attempts_requested_by", "repair_attempts", type_="foreignkey")
    op.drop_constraint("fk_repair_attempts_plan", "repair_attempts", type_="foreignkey")
    op.drop_column("repair_attempts", "error_message")
    op.drop_column("repair_attempts", "requested_by")
    op.drop_column("repair_attempts", "repair_plan_id")
    # PostgreSQL enum values cannot be removed safely while rows may use them.
    op.drop_index("ix_repositories_owner_name", table_name="repositories")
    op.create_index("ix_repositories_owner_name", "repositories", ["owner", "name"], unique=True)
    op.execute("DROP POLICY IF EXISTS patches_tenant_policy ON patches")
    op.execute("ALTER TABLE patches DISABLE ROW LEVEL SECURITY")
    op.drop_column("patches", "publish_error")
    op.drop_column("patches", "publish_status")
    op.drop_column("patches", "review_digest")
    op.drop_column("patches", "base_commit_sha")
    op.drop_column("patches", "branch_url")
