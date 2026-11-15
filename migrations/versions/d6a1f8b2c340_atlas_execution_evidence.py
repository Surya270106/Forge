"""Associate Atlas jobs with an execution Flight Recorder when requested.

Revision ID: d6a1f8b2c340
Revises: c4b7a9e1d620
"""

import sqlalchemy as sa
from alembic import op

revision = "d6a1f8b2c340"
down_revision = "c4b7a9e1d620"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("atlas_jobs", sa.Column("execution_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_atlas_job_execution", "atlas_jobs", "execution_jobs", ["execution_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_atlas_job_execution", "atlas_jobs", type_="foreignkey")
    op.drop_column("atlas_jobs", "execution_id")
