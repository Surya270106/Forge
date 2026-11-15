"""Add fenced execution ownership leases.

Revision ID: b2e7c4d9a150
Revises: a8e4c2b9d610
"""

import sqlalchemy as sa
from alembic import op

revision = "b2e7c4d9a150"
down_revision = "a8e4c2b9d610"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("execution_jobs", sa.Column("lease_owner", sa.String(length=128), nullable=True))
    op.add_column("execution_jobs", sa.Column("lease_generation", sa.Integer(), server_default="0", nullable=False))
    op.add_column("execution_jobs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_exec_jobs_lease", "execution_jobs", ["status", "lease_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_exec_jobs_lease", table_name="execution_jobs")
    op.drop_column("execution_jobs", "lease_expires_at")
    op.drop_column("execution_jobs", "lease_generation")
    op.drop_column("execution_jobs", "lease_owner")
