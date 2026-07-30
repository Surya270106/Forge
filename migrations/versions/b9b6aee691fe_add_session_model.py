"""add_session_model

Revision ID: b9b6aee691fe
Revises: a1b2c3d4e5f6
Create Date: 2026-07-24 10:28:08.570043

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9b6aee691fe'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('sessions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('session_token', sa.String(length=255), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=False), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('ip_address', sa.String(length=255), nullable=True),
    sa.Column('user_agent', sa.String(length=512), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sessions_session_token'), 'sessions', ['session_token'], unique=True)
    
    op.create_table('oauth_states',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('state', sa.String(length=255), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=False), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_oauth_states_state'), 'oauth_states', ['state'], unique=True)

def downgrade() -> None:
    op.drop_index(op.f('ix_oauth_states_state'), table_name='oauth_states')
    op.drop_table('oauth_states')
    op.drop_index(op.f('ix_sessions_session_token'), table_name='sessions')
    op.drop_table('sessions')
