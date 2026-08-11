import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin
from app.models.catalog import Title


class List(Base, CreatedAtMixin):
    """watchlist: one per user, created lazily. shared: tenant-wide, no owner.
    custom: user-created and nameable."""

    __tablename__ = "lists"
    __table_args__ = (Index("ix_lists_tenant_kind", "tenant_id", "kind"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(12))  # watchlist | custom | shared

    items: Mapped[list["ListItem"]] = relationship(
        back_populates="list", cascade="all, delete-orphan"
    )


class ListItem(Base):
    __tablename__ = "list_items"
    __table_args__ = (
        UniqueConstraint("list_id", "title_id", name="uq_list_items_list_id_title_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    list_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lists.id", ondelete="CASCADE"))
    title_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("titles.id", ondelete="CASCADE"), index=True
    )
    added_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # Where this sits in the list. Set when a whole franchise is saved in
    # release order; null for anything added one at a time, which then falls
    # back to sorting by when it was added.
    position: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(String(500))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    list: Mapped[List] = relationship(back_populates="items")
    title: Mapped[Title] = relationship()


class WatchEvent(Base):
    __tablename__ = "watch_events"
    __table_args__ = (
        CheckConstraint(
            "rating_10 IS NULL OR (rating_10 >= 1 AND rating_10 <= 10)",
            name="rating_range",
        ),
        Index("ix_watch_events_user_watched", "user_id", "watched_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("titles.id", ondelete="CASCADE"), index=True
    )
    # Which episode, when the watch was of one. Null for a film, and null for
    # a series watched before episodes existed, so history and stats keep
    # counting exactly as they did. The series is still named by title_id, so
    # nothing that reads this table needs to know about episodes at all.
    episode_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), index=True
    )
    watched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    rating_10: Mapped[int | None] = mapped_column(Integer)
    loved: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(12), default="app")  # app | import
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    title: Mapped[Title] = relationship()
