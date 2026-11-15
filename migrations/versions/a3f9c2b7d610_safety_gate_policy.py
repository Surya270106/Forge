"""Persist versioned Safety Gate restrictions and immutable execution snapshots.

Revision ID: a3f9c2b7d610
Revises: f8a2d9c1e430
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "a3f9c2b7d610"
down_revision = "f8a2d9c1e430"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "safety_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("denied", JSONB(), nullable=False),
        sa.Column("repository_denies", JSONB(), nullable=False),
        sa.Column("stopped", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "version", name="uq_safety_policy_version"),
    )
    op.execute("ALTER TABLE safety_policies ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE safety_policies FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY safety_policies_tenant_policy ON safety_policies
        USING (current_user = 'forge_admin' OR organization_id::text = current_setting('forge.organization_id', true))
        WITH CHECK (current_user = 'forge_admin' OR organization_id::text = current_setting('forge.organization_id', true))""")
    op.execute("""CREATE FUNCTION forbid_safety_policy_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Safety policy history is immutable'; END; $$""")
    op.execute("""CREATE TRIGGER safety_policy_history_immutable BEFORE UPDATE OR DELETE ON safety_policies
        FOR EACH ROW EXECUTE FUNCTION forbid_safety_policy_mutation()""")
    op.add_column("execution_jobs", sa.Column("safety_policy_snapshot", JSONB(), nullable=True))
    op.execute("""CREATE FUNCTION forbid_safety_snapshot_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF OLD.safety_policy_snapshot IS NOT NULL
            AND NEW.safety_policy_snapshot IS DISTINCT FROM OLD.safety_policy_snapshot
            THEN RAISE EXCEPTION 'Execution safety snapshots are immutable'; END IF;
            RETURN NEW;
        END; $$""")
    op.execute("""CREATE TRIGGER execution_safety_snapshot_immutable BEFORE UPDATE ON execution_jobs
        FOR EACH ROW EXECUTE FUNCTION forbid_safety_snapshot_mutation()""")


def downgrade() -> None:
    op.execute("DROP TRIGGER safety_policy_history_immutable ON safety_policies")
    op.execute("DROP FUNCTION forbid_safety_policy_mutation()")
    op.execute("DROP TRIGGER execution_safety_snapshot_immutable ON execution_jobs")
    op.execute("DROP FUNCTION forbid_safety_snapshot_mutation()")
    op.drop_column("execution_jobs", "safety_policy_snapshot")
    op.drop_table("safety_policies")
