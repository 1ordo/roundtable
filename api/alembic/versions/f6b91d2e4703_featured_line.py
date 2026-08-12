"""one line, featured at the top of a profile

Revision ID: f6b91d2e4703
Revises: e5a70c31f8b6
Create Date: 2026-08-12

A list of every line somebody saved is an inventory. One line they chose to
put at the top of their profile is a statement about them, which is what the
feature was reaching for.

The column lives on the user rather than as a flag on the quote, because
"one per person" is then the schema saying it rather than a constraint plus
a rule the code has to remember. Deleting the quote clears the feature
instead of cascading the user away, which is why it is SET NULL.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6b91d2e4703"
down_revision: str | None = "e5a70c31f8b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("featured_quote_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_users_featured_quote_id",
        "users",
        "quotes",
        ["featured_quote_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_featured_quote_id", "users", type_="foreignkey")
    op.drop_column("users", "featured_quote_id")
