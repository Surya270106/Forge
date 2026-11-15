"""Persist tenant-scoped benchmark runs and immutable trial results.

Revision ID: f8a2d9c1e430
Revises: e7c0a6d5b421
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "f8a2d9c1e430"
down_revision = "e7c0a6d5b421"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "benchmark_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("suite_id", sa.String(64), nullable=False),
        sa.Column("suite_version", sa.Integer(), nullable=False),
        sa.Column("dataset_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("manifest", JSONB(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("baseline_run_id", sa.Uuid(), sa.ForeignKey("benchmark_runs.id")),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_benchmark_run_request"),
    )
    op.create_index("ix_benchmark_runs_org_created", "benchmark_runs", ["organization_id", "created_at"])
    op.create_table(
        "benchmark_trials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("benchmark_runs.id"), nullable=False),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("task_version", sa.Integer(), nullable=False),
        sa.Column("repetition", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("execution_id", sa.Uuid(), sa.ForeignKey("execution_jobs.id")),
        sa.Column("plan_id", sa.Uuid(), sa.ForeignKey("plans.id")),
        sa.Column("base_commit", sa.String(40), nullable=False),
        sa.Column("patch_digest", sa.String(64)),
        sa.Column("result", JSONB()),
        sa.Column("failure_category", sa.String(32)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", "task_id", "repetition", name="uq_benchmark_trial_slot"),
        sa.UniqueConstraint("execution_id", name="uq_benchmark_trial_execution"),
    )
    op.create_index("ix_benchmark_trials_org_run", "benchmark_trials", ["organization_id", "run_id"])
    for table in ("benchmark_runs", "benchmark_trials"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""CREATE POLICY {table}_tenant_policy ON {table}
            USING (current_user = 'forge_admin' OR organization_id::text = current_setting('forge.organization_id', true))
            WITH CHECK (current_user = 'forge_admin' OR organization_id::text = current_setting('forge.organization_id', true))""")
    op.execute("""CREATE FUNCTION forbid_benchmark_result_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF OLD.result IS NOT NULL AND (NEW.result IS DISTINCT FROM OLD.result OR NEW.patch_digest IS DISTINCT FROM OLD.patch_digest)
            THEN RAISE EXCEPTION 'Benchmark results are immutable'; END IF;
            RETURN NEW;
        END; $$""")
    op.execute("""CREATE TRIGGER benchmark_results_immutable BEFORE UPDATE ON benchmark_trials
        FOR EACH ROW EXECUTE FUNCTION forbid_benchmark_result_mutation()""")
    op.execute("""CREATE FUNCTION forbid_benchmark_manifest_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF NEW.manifest IS DISTINCT FROM OLD.manifest OR NEW.dataset_digest IS DISTINCT FROM OLD.dataset_digest
            OR NEW.suite_id IS DISTINCT FROM OLD.suite_id OR NEW.suite_version IS DISTINCT FROM OLD.suite_version
            THEN RAISE EXCEPTION 'Benchmark manifests are immutable'; END IF;
            RETURN NEW;
        END; $$""")
    op.execute("""CREATE TRIGGER benchmark_manifests_immutable BEFORE UPDATE ON benchmark_runs
        FOR EACH ROW EXECUTE FUNCTION forbid_benchmark_manifest_mutation()""")


def downgrade() -> None:
    op.drop_table("benchmark_trials")
    op.drop_table("benchmark_runs")
    op.execute("DROP FUNCTION forbid_benchmark_result_mutation()")
    op.execute("DROP FUNCTION forbid_benchmark_manifest_mutation()")
