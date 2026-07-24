"""add patch model

Revision ID: 2a5451752ded
Revises: b767ac9b5115
Create Date: 2026-07-24 08:54:31.630351

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '2a5451752ded'
down_revision: str | None = 'b767ac9b5115'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


from sqlalchemy.dialects import postgresql


def upgrade() -> None:
    op.create_table(
        'patches',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('repository_id', sa.Uuid(), nullable=False),
        sa.Column('execution_job_id', sa.Uuid(), nullable=False),
        sa.Column('task_id', sa.Uuid(), nullable=True),
        sa.Column('status', postgresql.ENUM('GENERATED', 'UNDER_REVIEW', 'ACCEPTED', 'REJECTED', 'SUPERSEDED', 'APPLIED_TO_BRANCH', 'COMMITTED', 'PULL_REQUEST_CREATED', 'FAILED', name='patch_status'), nullable=False),
        sa.Column('total_additions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_deletions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('files_changed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('pull_request_url', sa.String(length=500), nullable=True),
        sa.Column('pull_request_number', sa.Integer(), nullable=True),
        sa.Column('branch_name', sa.String(length=255), nullable=True),
        sa.Column('commit_sha', sa.String(length=40), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reviewed_by', sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(['execution_job_id'], ['execution_jobs.id'], ),
        sa.ForeignKeyConstraint(['repository_id'], ['repositories.id'], ),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_patches_exec', 'patches', ['execution_job_id'], unique=False)
    op.create_index('ix_patches_repo_org', 'patches', ['repository_id', 'organization_id'], unique=False)
    op.create_index('ix_patches_status', 'patches', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_patches_status', table_name='patches')
    op.drop_index('ix_patches_repo_org', table_name='patches')
    op.drop_index('ix_patches_exec', table_name='patches')
    op.drop_table('patches')
    op.execute("DROP TYPE patch_status;")
