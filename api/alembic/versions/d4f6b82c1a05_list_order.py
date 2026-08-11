"""lists remember the order things were put in

Revision ID: d4f6b82c1a05
Revises: c3e5a71b9d42
Create Date: 2026-08-11

Adding a franchise to a list produced it backwards. list_items had no
ordering of its own and the items endpoint sorted by added_at descending, so
eight films saved in release order came back newest first, which for a
watch-through is exactly wrong.

added_at cannot be pressed into service instead: a bulk add writes the whole
set inside one transaction and the timestamps are identical, so the order
within them is whatever Postgres returns.

Nullable, because every existing row has no meaningful position and
inventing one would be a guess. Rows without a position keep sorting by
added_at, which is the behaviour they have always had.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4f6b82c1a05"
down_revision: str | None = "c3e5a71b9d42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("list_items", sa.Column("position", sa.Integer(), nullable=True))
    op.create_index("ix_list_items_list_position", "list_items", ["list_id", "position"])


def downgrade() -> None:
    op.drop_index("ix_list_items_list_position", table_name="list_items")
    op.drop_column("list_items", "position")
