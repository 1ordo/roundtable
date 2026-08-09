import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin

EMBED_DIM = 768  # nomic-embed-text-v1.5


class TitleEmbedding(Base, CreatedAtMixin):
    __tablename__ = "title_embeddings"

    title_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("titles.id", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[str] = mapped_column(String(200))
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBED_DIM))


class TitleAITag(Base, CreatedAtMixin):
    """Zero-shot vibe tags: cosine similarity between the title embedding and
    curated label centroids. Deterministic and reproducible."""

    __tablename__ = "title_ai_tags"
    __table_args__ = (
        UniqueConstraint("title_id", "tag", "source", name="uq_title_ai_tags_title_tag_source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("titles.id", ondelete="CASCADE"), index=True
    )
    tag: Mapped[str] = mapped_column(String(60))
    source: Mapped[str] = mapped_column(String(12), default="ai")  # ai | tmdb
    model: Mapped[str | None] = mapped_column(String(200))
    score: Mapped[float | None] = mapped_column(Float)
    # Structured payload for tags that carry more than a name and a score,
    # such as the content advisory breakdown.
    detail: Mapped[dict | None] = mapped_column(JSONB)


class LabelEmbedding(Base, CreatedAtMixin):
    """Embedded label descriptions, keyed by label and model so switching the
    embedding model recomputes them once."""

    __tablename__ = "label_embeddings"
    __table_args__ = (UniqueConstraint("tag", "model", name="uq_label_embeddings_tag_model"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tag: Mapped[str] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(200))
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBED_DIM))


class UserTaste(Base):
    """Cached taste centroid per user, recomputed when history changes."""

    __tablename__ = "user_tastes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[str] = mapped_column(String(200))
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBED_DIM))
    events_count: Mapped[int] = mapped_column(Integer, default=0)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
