"""update verification models

Revision ID: b767ac9b5115
Revises: ac3a21d5e8f0
Create Date: 2026-07-24 08:49:56.972871

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b767ac9b5115"
down_revision: str | None = "ac3a21d5e8f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


from sqlalchemy.dialects import postgresql


def upgrade() -> None:
    # New Enum for RepairAttemptStatus
    op.execute(
        "CREATE TYPE repair_attempt_status AS ENUM ('NOT_ELIGIBLE', 'ELIGIBLE', 'QUEUED', 'PLANNING', 'EXECUTING', 'REVERIFYING', 'SUCCEEDED', 'FAILED', 'EXHAUSTED', 'CANCELLED');"
    )

    # Add values to verification_status enum
    op.execute("ALTER TYPE verification_status ADD VALUE IF NOT EXISTS 'WARNING';")
    op.execute("ALTER TYPE verification_status ADD VALUE IF NOT EXISTS 'SKIPPED';")
    op.execute("ALTER TYPE verification_status ADD VALUE IF NOT EXISTS 'BLOCKED';")
    op.execute("ALTER TYPE verification_status ADD VALUE IF NOT EXISTS 'NOT_CONFIGURED';")
    op.execute("ALTER TYPE verification_status ADD VALUE IF NOT EXISTS 'CANCELLED';")
    op.execute("ALTER TYPE verification_status ADD VALUE IF NOT EXISTS 'TIMED_OUT';")

    # Drop old enum from verification_results if needed, but wait it's just a column drop
    op.drop_column("verification_results", "diagnostic_type")

    # Add new columns to verification_results
    op.add_column("verification_results", sa.Column("execution_id", sa.Uuid(), nullable=True))
    op.add_column("verification_results", sa.Column("verifier", sa.String(length=100), nullable=True))
    op.add_column("verification_results", sa.Column("duration_ms", sa.Integer(), nullable=True))
    op.add_column("verification_results", sa.Column("exit_code", sa.Integer(), nullable=True))
    op.add_column("verification_results", sa.Column("stdout", sa.Text(), nullable=True))
    op.add_column("verification_results", sa.Column("stderr", sa.Text(), nullable=True))
    op.add_column("verification_results", sa.Column("stdout_truncated", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("verification_results", sa.Column("stderr_truncated", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("verification_results", sa.Column("diagnostics", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False))
    op.add_column("verification_results", sa.Column("blocking", sa.Boolean(), server_default="true", nullable=False))
    op.add_column("verification_results", sa.Column("attempt", sa.Integer(), server_default="1", nullable=False))

    # Drop old columns
    op.drop_column("verification_results", "is_passed")
    op.drop_column("verification_results", "output")
    op.drop_column("verification_results", "parsed_diagnostics")

    # Add constraints
    op.create_foreign_key(None, "verification_results", "execution_jobs", ["execution_id"], ["id"])

    # Add columns to repair_attempts
    op.add_column("repair_attempts", sa.Column("status", postgresql.ENUM(name="repair_attempt_status", create_type=False), nullable=True))
    op.add_column("repair_attempts", sa.Column("attempt_number", sa.Integer(), server_default="1", nullable=False))

    # Drop old columns from repair_attempts
    op.drop_column("repair_attempts", "is_successful")
    op.alter_column("repair_attempts", "repair_execution_id", existing_type=sa.Uuid(), nullable=True)
    op.alter_column("repair_attempts", "prompt_used", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    pass
