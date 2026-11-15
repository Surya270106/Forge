"""Persist user cancellation intent on execution jobs.

Revision ID: e7c0a6d5b421
Revises: d4e8a3c1b902
"""

import sqlalchemy as sa
from alembic import op

revision = "e7c0a6d5b421"
down_revision = "d4e8a3c1b902"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE plan_status ADD VALUE IF NOT EXISTS 'CANCELLED'")
    op.add_column("execution_jobs", sa.Column("cancellation_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("execution_jobs", sa.Column("cancellation_requested_by", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_execution_cancel_requested_by", "execution_jobs", "users",
                          ["cancellation_requested_by"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_execution_cancel_requested_by", "execution_jobs", type_="foreignkey")
    op.drop_column("execution_jobs", "cancellation_requested_by")
    op.drop_column("execution_jobs", "cancellation_requested_at")
    # PostgreSQL enum values cannot be removed while existing plans may use them.
