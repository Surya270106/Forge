"""Restore patch reviewer foreign key on installations that retained patches.

Revision ID: d4e8a3c1b902
Revises: c9f2a6b8d741
"""

import sqlalchemy as sa
from alembic import op

revision = "d4e8a3c1b902"
down_revision = "c9f2a6b8d741"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    reviewer_fks = [fk for fk in sa.inspect(bind).get_foreign_keys("patches")
                    if fk["constrained_columns"] == ["reviewed_by"]]
    if reviewer_fks:
        if (len(reviewer_fks) != 1 or reviewer_fks[0]["referred_table"] != "users"
                or reviewer_fks[0]["referred_columns"] != ["id"]
                or reviewer_fks[0].get("options", {}).get("ondelete") not in (None, "NO ACTION")):
            raise RuntimeError("Unexpected patches reviewer foreign key; inspect schema manually")
        return
    orphans = bind.execute(sa.text("""
        SELECT patches.id FROM patches
        LEFT JOIN users ON users.id = patches.reviewed_by
        WHERE patches.reviewed_by IS NOT NULL AND users.id IS NULL
        ORDER BY patches.id LIMIT 10
    """)).scalars().all()
    if orphans:
        raise RuntimeError(
            "Cannot add patches reviewer foreign key; orphan patch IDs: "
            + ", ".join(str(value) for value in orphans)
        )
    op.create_foreign_key(
        "fk_patches_reviewed_by_users", "patches", "users", ["reviewed_by"], ["id"]
    )


def downgrade() -> None:
    if any(fk["name"] == "fk_patches_reviewed_by_users" for fk in sa.inspect(op.get_bind()).get_foreign_keys("patches")):
        op.drop_constraint("fk_patches_reviewed_by_users", "patches", type_="foreignkey")
