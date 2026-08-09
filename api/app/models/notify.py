import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin
from app.models.catalog import Title


class Notification(Base, CreatedAtMixin):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_read", "user_id", "read_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # availability
    title_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("titles.id", ondelete="SET NULL"))
    # Which episode this is about, for the new-episode alert. Also the dedupe
    # key: one notice per person per episode, enforced by looking here rather
    # than by digging through payload JSON.
    episode_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), index=True
    )
    message: Mapped[str] = mapped_column(String(500))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_via: Mapped[list] = mapped_column(JSONB, default=list)

    title: Mapped[Title | None] = relationship()
