"""certifications and collections

Revision ID: 6940981598b0
Revises: c1a7f2search
Create Date: 2026-08-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "6940981598b0"
down_revision: str | None = "c1a7f2search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default backfills the rows already in the table; the ORM always
    # supplies the value, so the default is dropped again straight after.
    op.add_column(
        "titles",
        sa.Column(
            "certifications",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column("titles", "certifications", server_default=None)
    op.add_column("titles", sa.Column("collection_id", sa.Integer(), nullable=True))
    op.add_column("titles", sa.Column("collection_name", sa.String(length=300), nullable=True))
    op.create_index("ix_titles_collection_id", "titles", ["collection_id"], unique=False)
    # The search and shelf indexes from c1a7f2search are hand written, so
    # autogenerate does not see them in the model metadata. They stay.


def downgrade() -> None:
    op.drop_index("ix_titles_collection_id", table_name="titles")
    op.drop_column("titles", "collection_name")
    op.drop_column("titles", "collection_id")
    op.drop_column("titles", "certifications")
