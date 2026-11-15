"""Immutable run capsule snapshots and bounded artifacts.

Revision ID: a4d1e8c2b930
Revises: f2c7d4e9a110
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "a4d1e8c2b930"
down_revision = "f2c7d4e9a110"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_execution_job_capsule_scope", "execution_jobs",
                                ["id", "organization_id", "repository_id"])
    op.create_table(
        "run_capsules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("repository_id", sa.Uuid(), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("execution_job_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("execution_events.id"), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(12), nullable=False),
        sa.Column("manifest", JSONB(), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("event_id", name="uq_run_capsule_event"),
        sa.UniqueConstraint("id", "organization_id", name="uq_run_capsule_scope"),
        sa.CheckConstraint("state IN ('PARTIAL', 'FINAL')", name="ck_run_capsule_state"),
        sa.ForeignKeyConstraint(["execution_job_id", "organization_id", "repository_id"],
                                ["execution_jobs.id", "execution_jobs.organization_id", "execution_jobs.repository_id"],
                                name="fk_run_capsule_execution_scope"),
    )
    op.create_index("ix_run_capsule_execution", "run_capsules",
                    ["organization_id", "execution_job_id", "attempt", "created_at"])
    op.create_table(
        "run_capsule_artifacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("capsule_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.UniqueConstraint("capsule_id", "kind", name="uq_run_capsule_artifact_kind"),
        sa.CheckConstraint("size_bytes BETWEEN 0 AND 16384", name="ck_run_capsule_artifact_size"),
        sa.ForeignKeyConstraint(["capsule_id", "organization_id"],
                                ["run_capsules.id", "run_capsules.organization_id"],
                                name="fk_run_capsule_artifact_scope"),
    )
    for table in ("run_capsules", "run_capsule_artifacts"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""CREATE POLICY {table}_tenant_policy ON {table}
            USING (current_user = 'forge_admin' OR organization_id::text = current_setting('forge.organization_id', true))
            WITH CHECK (current_user = 'forge_admin' OR organization_id::text = current_setting('forge.organization_id', true))""")
        op.execute(f"""CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION forbid_execution_event_mutation()""")


def downgrade() -> None:
    op.drop_table("run_capsule_artifacts")
    op.drop_table("run_capsules")
    op.drop_constraint("uq_execution_job_capsule_scope", "execution_jobs", type_="unique")
