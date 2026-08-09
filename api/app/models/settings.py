import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin


class AISettings(Base, CreatedAtMixin):
    """One row per tenant. The whole AI stack reads its endpoint from here so
    the app keeps working with AI disabled or unreachable."""

    __tablename__ = "ai_settings"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    base_url: Mapped[str] = mapped_column(String(400), default="http://localhost:11434/v1")
    chat_model: Mapped[str] = mapped_column(String(200), default="gemma-4-26b-a4b-it")
    # Set to the local encoder name to run recommendations with no external
    # embedding service at all.
    embed_model: Mapped[str] = mapped_column(
        String(200), default="roundtable-local-hashed-ngrams-v1"
    )
    api_key_enc: Mapped[str | None] = mapped_column(String(800))


class QuotaUsage(Base):
    """Daily request counters for external APIs, shown in admin."""

    __tablename__ = "quota_usage"
    __table_args__ = (UniqueConstraint("source", "day", name="uq_quota_usage_source_day"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(20))  # tmdb | omdb
    day: Mapped[date] = mapped_column(Date)
    count: Mapped[int] = mapped_column(Integer, default=0)


class FeatureFlag(Base, CreatedAtMixin):
    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict | None] = mapped_column(JSONB)
