"""Direct messages, between friends.

Friends only, deliberately. An app where anyone can message anyone needs
blocking, reporting and moderation to be safe, and none of that is worth
building for a household and the people they invited. Accepting a friend
request is the consent to be messaged.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth.deps import csrf_protect, get_current_user
from app.db import get_db
from app.models import DirectMessage, User
from app.social import visibility

router = APIRouter(prefix="/api")

MAX_BODY = 2000


class Correspondent(BaseModel):
    handle: str | None
    display_name: str | None
    username: str
    avatar_path: str | None


class MessageOut(BaseModel):
    id: str
    body: str
    created_at: datetime
    mine: bool
    read: bool
    title: dict | None = None


class ThreadOut(BaseModel):
    person: Correspondent
    messages: list[MessageOut]


class ConversationOut(BaseModel):
    person: Correspondent
    last: str
    last_at: datetime
    unread: int
    from_them: bool


class SendBody(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_BODY)
    # Optional "have you seen this", which is most of what anyone sends.
    type: str | None = None
    tmdb_id: int | None = None


def _person(user: User) -> Correspondent:
    return Correspondent(
        handle=user.handle,
        display_name=user.display_name,
        username=user.username,
        avatar_path=user.avatar_path,
    )


def _message(row: DirectMessage, viewer: User) -> MessageOut:
    return MessageOut(
        id=str(row.id),
        body=row.body,
        created_at=row.created_at,
        mine=row.sender_id == viewer.id,
        read=row.read_at is not None,
        title=(
            {
                "tmdb_id": row.title.tmdb_id,
                "type": row.title.type,
                "name": row.title.name,
                "poster_path": row.title.poster_path,
                "year": row.title.year,
            }
            if row.title is not None
            else None
        ),
    )


async def _friend_or_404(db: AsyncSession, viewer: User, handle: str) -> User:
    """The person, if they are a friend. Not "forbidden": whether a handle
    exists is not something a stranger needs confirmed."""
    other = (
        await db.execute(
            select(User).where(
                func.lower(User.handle) == handle.lower().lstrip("@"),
                User.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if other is None or other.id == viewer.id:
        raise HTTPException(status_code=404, detail="no one by that name")
    if other.id not in await visibility.friend_ids(db, viewer):
        raise HTTPException(status_code=404, detail="you are not friends yet")
    return other


@router.get("/messages", response_model=list[ConversationOut])
async def conversations(
    viewer: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[ConversationOut]:
    """One row per person, newest first.

    Done in Python over the viewer's own messages rather than as a window
    function, because a household's message count is small and the query
    stays readable."""
    rows = (
        (
            await db.execute(
                select(DirectMessage)
                .options(joinedload(DirectMessage.sender), joinedload(DirectMessage.recipient))
                .where(
                    or_(
                        DirectMessage.sender_id == viewer.id,
                        DirectMessage.recipient_id == viewer.id,
                    )
                )
                .order_by(DirectMessage.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    seen: dict[uuid.UUID, ConversationOut] = {}
    for row in rows:
        other = row.recipient if row.sender_id == viewer.id else row.sender
        entry = seen.get(other.id)
        if entry is None:
            entry = ConversationOut(
                person=_person(other),
                last=row.body[:120],
                last_at=row.created_at,
                unread=0,
                from_them=row.sender_id != viewer.id,
            )
            seen[other.id] = entry
        # Unread only counts what they sent you.
        if row.recipient_id == viewer.id and row.read_at is None:
            entry.unread += 1

    await db.commit()
    return list(seen.values())


@router.get("/messages/{handle}", response_model=ThreadOut)
async def thread(
    handle: str,
    viewer: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(80, le=200),
) -> ThreadOut:
    """The conversation, oldest last, and everything from them marked read."""
    other = await _friend_or_404(db, viewer, handle)
    rows = (
        (
            await db.execute(
                select(DirectMessage)
                .options(joinedload(DirectMessage.title))
                .where(
                    or_(
                        (DirectMessage.sender_id == viewer.id)
                        & (DirectMessage.recipient_id == other.id),
                        (DirectMessage.sender_id == other.id)
                        & (DirectMessage.recipient_id == viewer.id),
                    )
                )
                .order_by(DirectMessage.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    # Opening the thread is reading it.
    await db.execute(
        update(DirectMessage)
        .where(
            DirectMessage.sender_id == other.id,
            DirectMessage.recipient_id == viewer.id,
            DirectMessage.read_at.is_(None),
        )
        .values(read_at=datetime.now(UTC))
    )
    await db.commit()

    return ThreadOut(
        person=_person(other),
        messages=[_message(row, viewer) for row in reversed(rows)],
    )


@router.post(
    "/messages/{handle}",
    response_model=MessageOut,
    status_code=201,
    dependencies=[Depends(csrf_protect)],
)
async def send(
    handle: str,
    body: SendBody,
    request: Request,
    viewer: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    other = await _friend_or_404(db, viewer, handle)
    text = body.body.strip()
    if not text:
        raise HTTPException(status_code=422, detail="say something")

    title = None
    if body.type and body.tmdb_id:
        from app.catalog import ingest

        if body.type not in ("movie", "tv"):
            raise HTTPException(status_code=404, detail="unknown media type")
        title = await ingest.ensure_title(db, body.type, body.tmdb_id)

    message = DirectMessage(
        sender_id=viewer.id,
        recipient_id=other.id,
        body=text,
        title_id=title.id if title else None,
    )
    db.add(message)
    await db.flush()

    # An inbox row so it is not missed, and so the existing push and email
    # channels carry it without any new plumbing.
    from app.notifications import service as notifications

    who = viewer.display_name or (f"@{viewer.handle}" if viewer.handle else viewer.username)
    await notifications.notify(
        db,
        other,
        "message",
        f"{who}: {text[:120]}",
        title=title,
        payload={"from": viewer.handle or viewer.username},
        push_title="A message",
    )

    await db.commit()
    loaded = (
        await db.execute(
            select(DirectMessage)
            .options(joinedload(DirectMessage.title))
            .where(DirectMessage.id == message.id)
        )
    ).scalar_one()
    return _message(loaded, viewer)


@router.get("/messages-unread")
async def unread_count(
    viewer: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    total = (
        await db.execute(
            select(func.count(DirectMessage.id)).where(
                DirectMessage.recipient_id == viewer.id, DirectMessage.read_at.is_(None)
            )
        )
    ).scalar_one()
    return {"unread": int(total or 0)}
