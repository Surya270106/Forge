"""add_plan_revisions

Revision ID: e8f3b1a2c3d4
Revises: 2a5451752ded
Create Date: 2026-07-24 09:25:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'e8f3b1a2c3d4'
down_revision = '2a5451752ded'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('plans', sa.Column('parent_plan_id', sa.Uuid(), nullable=True))
    op.add_column('plans', sa.Column('feedback', sa.Text(), nullable=True))
    op.create_foreign_key('fk_plans_parent_plan_id', 'plans', 'plans', ['parent_plan_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_plans_parent_plan_id', 'plans', type_='foreignkey')
    op.drop_column('plans', 'feedback')
    op.drop_column('plans', 'parent_plan_id')
