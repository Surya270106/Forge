"""Durable tenant-scoped, append-only execution timeline.

Revision ID: c9f2a6b8d741
Revises: b2e7c4d9a150
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "c9f2a6b8d741"
down_revision = "b2e7c4d9a150"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "execution_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("execution_job_id", sa.Uuid(), sa.ForeignKey("execution_jobs.id"), nullable=False),
        sa.Column("task_node_id", sa.Uuid(), sa.ForeignKey("task_nodes.id"), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_type", sa.String(30), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=True),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("summary", sa.String(160), nullable=False),
        sa.Column("data", JSONB(), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=True),
        sa.Column("causation_id", sa.String(128), nullable=True),
        sa.Column("idempotency_key", sa.String(160), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("execution_job_id", "sequence", name="uq_execution_event_sequence"),
        sa.UniqueConstraint("execution_job_id", "idempotency_key", name="uq_execution_event_idempotency"),
    )
    op.create_index("ix_execution_events_timeline", "execution_events", ["organization_id", "execution_job_id", "sequence"])
    op.execute("ALTER TABLE execution_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE execution_events FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY execution_events_tenant_policy ON execution_events
        USING (current_user = 'forge_admin' OR organization_id::text = current_setting('forge.organization_id', true))
        WITH CHECK (current_user = 'forge_admin' OR organization_id::text = current_setting('forge.organization_id', true))""")
    op.execute("""CREATE FUNCTION forbid_execution_event_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Execution events are append-only'; END; $$""")
    op.execute("""CREATE TRIGGER execution_events_append_only BEFORE UPDATE OR DELETE ON execution_events
        FOR EACH ROW EXECUTE FUNCTION forbid_execution_event_mutation()""")


def downgrade() -> None:
    op.drop_table("execution_events")
    op.execute("DROP FUNCTION forbid_execution_event_mutation()")
