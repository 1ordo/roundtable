import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth.deps import csrf_protect, get_current_user
from app.db import get_db
from app.models import Notification, User

router = APIRouter(
    prefix="/api/notifications",
    dependencies=[Depends(get_current_user), Depends(csrf_protect)],
)


def _link_for(row) -> str | None:
    """Where a notification takes you.

    Ordered by how specific it is: a message goes to that conversation, a
    social row to the person who did it, and anything about a title to the
    title. A row with nowhere sensible to go returns None, and the
    interface leaves it unclickable rather than guessing."""
    payload = row.payload or {}
    sender = payload.get("from")
    if row.kind == "message" and sender:
        return f"/app/messages/{sender}"
    if row.kind in ("social", "like", "shared") and sender:
        return f"/app/u/{sender}"
    if row.title is not None:
        return f"/app/title/{row.title.type}/{row.title.tmdb_id}"
    if row.kind == "franchise" and payload.get("tmdb_id"):
        return f"/app/title/{payload.get('type', 'movie')}/{payload['tmdb_id']}"
    return None


class NotificationOut(BaseModel):
    id: str
    kind: str
    message: str
    payload: dict
    read: bool
    created_at: datetime
    title_tmdb_id: int | None
    title_type: str | None
    title_poster: str | None
    # Where clicking it should go. Worked out here rather than in the
    # browser, because the server is the side that knows what the row is
    # about.
    link: str | None = None


class InboxResponse(BaseModel):
    unread: int
    notifications: list[NotificationOut]


@router.get("", response_model=InboxResponse)
async def inbox(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> InboxResponse:
    unread = (
        await db.execute(
            select(func.count(Notification.id)).where(
                Notification.user_id == user.id, Notification.read_at.is_(None)
            )
        )
    ).scalar_one()
    rows = (
        (
            await db.execute(
                select(Notification)
                .options(joinedload(Notification.title))
                .where(Notification.user_id == user.id)
                .order_by(Notification.created_at.desc())
                .limit(100)
            )
        )
        .scalars()
        .all()
    )
    return InboxResponse(
        unread=unread,
        notifications=[
            NotificationOut(
                id=str(n.id),
                kind=n.kind,
                message=n.message,
                payload=n.payload or {},
                read=n.read_at is not None,
                created_at=n.created_at,
                title_tmdb_id=n.title.tmdb_id if n.title else None,
                title_type=n.title.type if n.title else None,
                title_poster=n.title.poster_path if n.title else None,
                link=_link_for(n),
            )
            for n in rows
        ],
    )


@router.post("/read-all", status_code=204)
async def mark_all_read(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    rows = (
        (
            await db.execute(
                select(Notification).where(
                    Notification.user_id == user.id, Notification.read_at.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    now = datetime.now(UTC)
    for row in rows:
        row.read_at = now
    await db.commit()


@router.post("/{notification_id}/read", status_code=204)
async def mark_read(
    notification_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        nid = uuid.UUID(notification_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="notification not found") from exc
    row = (
        await db.execute(
            select(Notification).where(Notification.id == nid, Notification.user_id == user.id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="notification not found")
    if row.read_at is None:
        row.read_at = datetime.now(UTC)
    await db.commit()
