"""an index for the vector search, and a handle for everyone

Revision ID: b2d4f6a80c33
Revises: a1c3e5f70b21
Create Date: 2026-08-09

Two unrelated fixes that both have to touch the database.

The index is the important one. Every shelf on the home page ranks titles by
cosine distance against the whole of title_embeddings, and with no index
Postgres computes that distance for every row and sorts. That is the reason
the home page needed a cache and a streaming response to feel bearable; this
addresses the cause rather than the symptom.

The handle backfill closes a gap that made most of the social features
unreachable: handles were optional, nothing assigned one, and a profile has
no address other than its handle. Accounts created before this migration
have none, so they are filled in here from the username.
"""

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2d4f6a80c33"
down_revision: str | None = "a1c3e5f70b21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RESERVED = {"admin", "api", "app", "auth", "me", "new", "root", "settings", "watchpile"}


def upgrade() -> None:
    # HNSW over IVFFlat: it needs no training pass, so it works on an empty
    # table and on one that grows continuously, which this one does. The
    # operator class must match the distance the query uses (cosine).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_title_embeddings_hnsw "
        "ON title_embeddings USING hnsw (embedding vector_cosine_ops)"
    )
    # Every vector query also filters on the model, and the planner needs a
    # cheap way to do that before it reaches the index.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_title_embeddings_model ON title_embeddings (model)"
    )

    # Backfill handles for accounts that predate automatic assignment.
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, username, email FROM users WHERE handle IS NULL")
    ).fetchall()
    taken = {
        row[0]
        for row in connection.execute(
            sa.text("SELECT handle FROM users WHERE handle IS NOT NULL")
        ).fetchall()
    }
    for user_id, username, email in rows:
        stem = (username or (email or "").split("@")[0] or "").strip().lower()
        stem = re.sub(r"[^a-z0-9_]+", "_", stem).strip("_")
        stem = re.sub(r"_+", "_", stem)
        stem = re.sub(r"^[^a-z]+", "", stem)[:24].rstrip("_")
        if len(stem) < 3:
            stem = f"{stem}_watcher"[:24] if stem else "watcher"
        if stem in RESERVED:
            stem = f"{stem}_1"
        candidate = stem
        suffix = 2
        while candidate in taken:
            tail = f"_{suffix}"
            candidate = stem[: 24 - len(tail)] + tail
            suffix += 1
        taken.add(candidate)
        connection.execute(
            sa.text("UPDATE users SET handle = :handle WHERE id = :id"),
            {"handle": candidate, "id": user_id},
        )


def downgrade() -> None:
    # The handles stay: taking someone's address away is not a rollback,
    # and nothing downstream breaks by having one.
    op.execute("DROP INDEX IF EXISTS ix_title_embeddings_model")
    op.execute("DROP INDEX IF EXISTS ix_title_embeddings_hnsw")
