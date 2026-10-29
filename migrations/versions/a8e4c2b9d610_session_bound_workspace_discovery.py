"""Allow session-bound workspace discovery through forced role-binding RLS.

Revision ID: a8e4c2b9d610
Revises: f74a1d2e3c60
"""

from alembic import op

revision = "a8e4c2b9d610"
down_revision = "f74a1d2e3c60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A random, active server-side session is the only cross-workspace discovery
    # capability. The caller cannot select another user via a supplied user ID.
    op.execute("""
        CREATE POLICY role_bindings_session_discovery ON role_bindings
        FOR SELECT TO PUBLIC
        USING (EXISTS (
            SELECT 1 FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.session_token = current_setting('forge.session_token', true)
              AND s.user_id = role_bindings.user_id
              AND s.is_active AND u.is_active
              AND s.expires_at > (now() AT TIME ZONE 'UTC')
        ))
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS role_bindings_session_discovery ON role_bindings")
