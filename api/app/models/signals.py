import uuid

from sqlalchemy import ForeignKey, Index, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin


class Interaction(Base, CreatedAtMixin):
    """Implicit and explicit signals: every click matters. The taste engine
    reads these alongside watch history."""

    __tablename__ = "interactions"
    __table_args__ = (
        Index("ix_interactions_user_title", "user_id", "title_id"),
        Index("ix_interactions_user_kind_created", "user_id", "kind", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("titles.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))  # view | click_out | like | dislike


class Group(Base, CreatedAtMixin):
    """A watch night: any set of members whose tastes get blended."""

    __tablename__ = "groups"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(120))
    member_ids: Mapped[list] = mapped_column(JSONB, default=list)  # user id strings
