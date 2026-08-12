"""repair the strings a project rename quietly changed

Revision ID: e5a70c31f8b6
Revises: d4f6b82c1a05
Create Date: 2026-08-11

Renaming the project rewrote several string literals that were not names at
all. They were identifiers with data keyed to them, and changing them broke
things silently, because nothing in the test suite compares a value written
before a change with one written after.

The local encoder was called "watchdeck-local-hashed-ngrams-v1". Every row
in title_embeddings is keyed by that string, and ai_settings.embed_model
holds it. After the rename the app looked for the new name, matched nothing,
concluded the configured model was not the local encoder, and tried to reach
an embedding endpoint that does not exist.

The AI key is handled in code rather than here, because it is encrypted and
the migration cannot read it: app/ai/crypto.py keeps the old salt and
re-seals on the next read.

Both rewrites are guarded, so running this on a database that never saw the
old name changes nothing.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5a70c31f8b6"
down_revision: str | None = "d4f6b82c1a05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_MODEL = "watchdeck-local-hashed-ngrams-v1"
NEW_MODEL = "roundtable-local-hashed-ngrams-v1"


def upgrade() -> None:
    connection = op.get_bind()
    for table in ("title_embeddings", "label_embeddings", "title_ai_tags"):
        connection.execute(
            sa.text(f"UPDATE {table} SET model = :new WHERE model = :old"),
            {"new": NEW_MODEL, "old": OLD_MODEL},
        )
    connection.execute(
        sa.text("UPDATE ai_settings SET embed_model = :new WHERE embed_model = :old"),
        {"new": NEW_MODEL, "old": OLD_MODEL},
    )


def downgrade() -> None:
    connection = op.get_bind()
    for table in ("title_embeddings", "label_embeddings", "title_ai_tags"):
        connection.execute(
            sa.text(f"UPDATE {table} SET model = :old WHERE model = :new"),
            {"new": NEW_MODEL, "old": OLD_MODEL},
        )
    connection.execute(
        sa.text("UPDATE ai_settings SET embed_model = :old WHERE embed_model = :new"),
        {"new": NEW_MODEL, "old": OLD_MODEL},
    )
