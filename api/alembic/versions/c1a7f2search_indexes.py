"""search and catalog indexes

Revision ID: c1a7f2search
Revises: b4fbd09fc9c3
Create Date: 2026-08-01

"""

from collections.abc import Sequence

from alembic import op

revision: str = "c1a7f2search"
down_revision: str | None = "b4fbd09fc9c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Trigram indexes make the ILIKE title search fast as the catalog grows.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE INDEX IF NOT EXISTS ix_titles_name_trgm ON titles USING gin (name gin_trgm_ops)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_titles_original_name_trgm "
        "ON titles USING gin (original_name gin_trgm_ops)"
    )
    # The rows that build every home shelf.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_titles_type_popularity "
        "ON titles (type, popularity DESC NULLS LAST)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_titles_language_popularity "
        "ON titles (original_language, popularity DESC NULLS LAST)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_titles_genres_gin ON titles USING gin (genres)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_titles_imdb_id ON titles (imdb_id)")


def downgrade() -> None:
    for index in (
        "ix_titles_name_trgm",
        "ix_titles_original_name_trgm",
        "ix_titles_type_popularity",
        "ix_titles_language_popularity",
        "ix_titles_genres_gin",
        "ix_titles_imdb_id",
    ):
        op.execute(f"DROP INDEX IF EXISTS {index}")
