import uuid

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin


class ImportBatch(Base, CreatedAtMixin):
    """One uploaded file or pasted payload.

    stats: {total, imported, ambiguous, unmatched, skipped}
    review_queue: [{index, raw, name, year, watched_at, candidates: [...], resolved}]
    """

    __tablename__ = "import_batches"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    service: Mapped[str] = mapped_column(String(30))  # netflix_history | netflix_mylist | json
    target: Mapped[str] = mapped_column(String(12))  # history | watchlist
    filename: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(12), default="pending")
    # pending | processing | review | done | failed
    error: Mapped[str | None] = mapped_column(String(500))
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)
    review_queue: Mapped[list] = mapped_column(JSONB, default=list)
    rows: Mapped[list] = mapped_column(JSONB, default=list)
