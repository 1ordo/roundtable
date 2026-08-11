"""full-text search over what a title is actually about

Revision ID: c3e5a71b9d42
Revises: b2d4f6a80c33
Create Date: 2026-08-11

Finding a film from a half-remembered plot did not work, and the reason was
not the rails around the assistant, it was retrieval. The default encoder is
lexical, so it compares the words two texts share. Measured against the real
catalog, "movie about a man stuck repeating one day" put Groundhog Day at
rank 13,614 of 21,018, which is worse than random.

The fix is not a bigger model. It is that TMDB keywords already hold the
vocabulary people actually use to describe a film: Groundhog Day carries
"time loop" and "deja vu", Inception carries "dream world" and
"subconscious". Inception's overview never contains the word "dream" at all,
which is why searching the plot text alone can never find it.

So: a tsvector over name, keywords and overview, keywords weighted highest.
Pure Postgres, no embedding endpoint, no network.

Two things that look right and are not:

  keywords is JSONB, and the obvious array_to_string(ARRAY(SELECT
  jsonb_array_elements_text(...))) is rejected outright, because a
  generated column may not contain a subquery. `keywords #>> '{}'` is
  IMMUTABLE, tokenises correctly, and preserves positions so phrase
  queries still work.

  Weights are assigned A to D with A highest, so keywords take A, the name
  takes B and the overview takes C. The ts_rank weight array is given in
  the order {D,C,B,A}, which is the reverse of how it reads.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c3e5a71b9d42"
down_revision: str | None = "b2d4f6a80c33"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE titles ADD COLUMN search_doc tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(keywords #>> '{}', '')), 'A')
            || setweight(to_tsvector('english', coalesce(name, '')), 'B')
            || setweight(to_tsvector('english', coalesce(original_name, '')), 'B')
            || setweight(to_tsvector('english', coalesce(overview, '')), 'C')
        ) STORED
        """
    )
    op.execute("CREATE INDEX ix_titles_search_doc ON titles USING gin (search_doc)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_titles_search_doc")
    op.execute("ALTER TABLE titles DROP COLUMN IF EXISTS search_doc")
