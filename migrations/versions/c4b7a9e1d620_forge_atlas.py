"""Persist tenant-scoped Forge Atlas jobs and immutable graph snapshots.

Revision ID: c4b7a9e1d620
Revises: a3f9c2b7d610
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "c4b7a9e1d620"
down_revision = "a3f9c2b7d610"
branch_labels = None
depends_on = None


def _base_columns() -> list[sa.Column]:
    return [sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("repository_id", sa.Uuid(), sa.ForeignKey("repositories.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    op.create_table(
        "atlas_jobs", *_base_columns(),
        sa.Column("requested_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("requested_revision", sa.String(40)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(120)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(60)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("organization_id", "repository_id", "idempotency_key", name="uq_atlas_job_request"),
        sa.UniqueConstraint("id", "organization_id", "repository_id", name="uq_atlas_job_scope"),
    )
    op.create_index("ix_atlas_jobs_repo_status", "atlas_jobs", ["organization_id", "repository_id", "status"])
    op.create_table(
        "atlas_snapshots", *_base_columns(),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("commit_sha", sa.String(40), nullable=False),
        sa.Column("tree_sha", sa.String(40), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("dirty", sa.Boolean(), nullable=False),
        sa.Column("indexer_version", sa.String(40), nullable=False),
        sa.Column("parser_versions", JSONB(), nullable=False),
        sa.Column("config_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("stats", JSONB(), nullable=False),
        sa.Column("warnings", JSONB(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("job_id", name="uq_atlas_snapshot_job"),
        sa.UniqueConstraint("id", "organization_id", "repository_id", name="uq_atlas_snapshot_scope"),
        sa.ForeignKeyConstraint(["job_id", "organization_id", "repository_id"],
                                ["atlas_jobs.id", "atlas_jobs.organization_id", "atlas_jobs.repository_id"], name="fk_atlas_snapshot_job_scope"),
    )
    op.create_index("ix_atlas_snapshots_repo_published", "atlas_snapshots", ["organization_id", "repository_id", "status", "completed_at"])
    op.create_table(
        "atlas_file_facts", *_base_columns(),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("fact", JSONB(), nullable=False),
        sa.UniqueConstraint("snapshot_id", "path", name="uq_atlas_fact_path"),
        sa.ForeignKeyConstraint(["snapshot_id", "organization_id", "repository_id"],
                                ["atlas_snapshots.id", "atlas_snapshots.organization_id", "atlas_snapshots.repository_id"], name="fk_atlas_fact_scope"),
    )
    op.create_table(
        "atlas_nodes", *_base_columns(),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("stable_key", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("path", sa.Text()),
        sa.Column("line_start", sa.Integer()),
        sa.Column("line_end", sa.Integer()),
        sa.Column("language", sa.String(32)),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("parser_version", sa.String(40)),
        sa.UniqueConstraint("snapshot_id", "stable_key", name="uq_atlas_node_key"),
        sa.UniqueConstraint("snapshot_id", "id", name="uq_atlas_node_snapshot_id"),
        sa.ForeignKeyConstraint(["snapshot_id", "organization_id", "repository_id"],
                                ["atlas_snapshots.id", "atlas_snapshots.organization_id", "atlas_snapshots.repository_id"], name="fk_atlas_node_scope"),
    )
    op.create_index("ix_atlas_nodes_search", "atlas_nodes", ["organization_id", "repository_id", "snapshot_id", "name"])
    op.create_table(
        "atlas_edges", *_base_columns(),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("from_node_id", sa.Uuid(), nullable=False),
        sa.Column("to_node_id", sa.Uuid()),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("target_name", sa.Text(), nullable=False),
        sa.Column("evidence_path", sa.Text(), nullable=False),
        sa.Column("evidence_line", sa.Integer(), nullable=False),
        sa.Column("resolution", sa.String(24), nullable=False),
        sa.Column("confidence", sa.String(12), nullable=False),
        sa.Column("method", sa.String(50), nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id", "organization_id", "repository_id"],
                                ["atlas_snapshots.id", "atlas_snapshots.organization_id", "atlas_snapshots.repository_id"], name="fk_atlas_edge_scope"),
        sa.ForeignKeyConstraint(["snapshot_id", "from_node_id"], ["atlas_nodes.snapshot_id", "atlas_nodes.id"], name="fk_atlas_edge_from_snapshot"),
        sa.ForeignKeyConstraint(["snapshot_id", "to_node_id"], ["atlas_nodes.snapshot_id", "atlas_nodes.id"], name="fk_atlas_edge_to_snapshot"),
    )
    op.create_index("ix_atlas_edges_reverse", "atlas_edges", ["snapshot_id", "to_node_id", "kind"])
    op.create_index("ix_atlas_edges_source", "atlas_edges", ["snapshot_id", "from_node_id"])
    for table in ("atlas_jobs", "atlas_snapshots", "atlas_file_facts", "atlas_nodes", "atlas_edges"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""CREATE POLICY {table}_tenant_policy ON {table}
            USING (current_user = 'forge_admin' OR organization_id::text = current_setting('forge.organization_id', true))
            WITH CHECK (current_user = 'forge_admin' OR organization_id::text = current_setting('forge.organization_id', true))""")
    op.execute("""CREATE FUNCTION forbid_published_atlas_snapshot_change() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF OLD.status = 'PUBLISHED' THEN RAISE EXCEPTION 'Published Atlas snapshot is immutable'; END IF;
        RETURN NEW; END; $$""")
    op.execute("""CREATE TRIGGER atlas_snapshot_immutable BEFORE UPDATE OR DELETE ON atlas_snapshots
        FOR EACH ROW EXECUTE FUNCTION forbid_published_atlas_snapshot_change()""")
    op.execute("""CREATE FUNCTION guard_atlas_graph_row() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'Atlas graph rows are immutable'; END IF;
        IF (SELECT status FROM atlas_snapshots WHERE id = NEW.snapshot_id) <> 'BUILDING'
            THEN RAISE EXCEPTION 'Atlas graph may only be built before publication'; END IF;
        RETURN NEW; END; $$""")
    for table in ("atlas_file_facts", "atlas_nodes", "atlas_edges"):
        op.execute(f"""CREATE TRIGGER {table}_immutable BEFORE INSERT OR UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION guard_atlas_graph_row()""")


def downgrade() -> None:
    for table in ("atlas_edges", "atlas_nodes", "atlas_file_facts"):
        op.execute(f"DROP TRIGGER {table}_immutable ON {table}")
    op.execute("DROP FUNCTION guard_atlas_graph_row()")
    op.execute("DROP TRIGGER atlas_snapshot_immutable ON atlas_snapshots")
    op.execute("DROP FUNCTION forbid_published_atlas_snapshot_change()")
    for table in ("atlas_edges", "atlas_nodes", "atlas_file_facts", "atlas_snapshots", "atlas_jobs"):
        op.drop_table(table)
