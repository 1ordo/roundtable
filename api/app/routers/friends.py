"""Friends, and the privacy that depends on them.

Nobody is connected to anybody without agreeing to it, and a profile is
private until its owner says otherwise. Those two rules decide what every
endpoint here is allowed to return."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import audit
from app.auth.deps import csrf_protect, get_current_user
from app.db import get_db
from app.models import Friendship, User
from app.notifications import service as notifications
from app.social import visibility

router = APIRouter(prefix="/api")


class PersonOut(BaseModel):
    id: str
    username: str
    # So every person in the app is a link to their profile.
    handle: str | None = None
    display_name: str | None = None
    avatar_path: str | None
    visibility: str
    # Where this person stands with you: none | pending_out | pending_in | friends
    relation: str = "none"


class FriendsPage(BaseModel):
    friends: list[PersonOut]
    incoming: list[PersonOut]
    outgoing: list[PersonOut]


async def friend_ids(db: AsyncSession, user: User) -> set[uuid.UUID]:
    """Everyone this person is actually friends with, both directions."""
    rows = (
        await db.execute(
            select(Friendship).where(
                Friendship.status == "accepted",
                or_(Friendship.requester_id == user.id, Friendship.addressee_id == user.id),
            )
        )
    ).scalars()
    out = set()
    for row in rows:
        out.add(row.addressee_id if row.requester_id == user.id else row.requester_id)
    return out


async def can_view(db: AsyncSession, viewer: User, subject: User) -> bool:
    """Kept as the name the routes already use. The rule itself lives in
    app/social/visibility.py so every surface answers the same way."""
    return await visibility.can_see(db, viewer, subject)


def _person(user: User, relation: str = "none") -> PersonOut:
    return PersonOut(
        id=str(user.id),
        username=user.username,
        handle=user.handle,
        display_name=user.display_name,
        avatar_path=user.avatar_path,
        visibility=user.visibility,
        relation=relation,
    )


@router.get("/friends", response_model=FriendsPage)
async def my_friends(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> FriendsPage:
    rows = (
        (
            await db.execute(
                select(Friendship).where(
                    or_(Friendship.requester_id == user.id, Friendship.addressee_id == user.id)
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return FriendsPage(friends=[], incoming=[], outgoing=[])

    other_ids = {r.addressee_id if r.requester_id == user.id else r.requester_id for r in rows}
    people = {
        u.id: u
        for u in (await db.execute(select(User).where(User.id.in_(other_ids)))).scalars().all()
    }

    friends, incoming, outgoing = [], [], []
    for row in rows:
        other = people.get(row.addressee_id if row.requester_id == user.id else row.requester_id)
        if other is None:
            continue
        if row.status == "accepted":
            friends.append(_person(other, "friends"))
        elif row.requester_id == user.id:
            outgoing.append(_person(other, "pending_out"))
        else:
            incoming.append(_person(other, "pending_in"))
    friends.sort(key=lambda p: p.username.lower())
    return FriendsPage(friends=friends, incoming=incoming, outgoing=outgoing)


# Deliberately not /people/search: /api/people/{id} already means a person
# in the catalog, and an account is a different kind of thing.
@router.get("/users/search", response_model=list[PersonOut])
async def find_people(
    q: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PersonOut]:
    """Find someone to add. Everyone in the same tenant is findable by name;
    what you can then see of them still depends on privacy."""
    term = q.strip()
    if len(term) < 2:
        return []
    found = (
        (
            await db.execute(
                select(User)
                .where(
                    User.tenant_id == user.tenant_id,
                    User.id != user.id,
                    User.is_active.is_(True),
                    User.username.ilike(f"%{term}%")
                    | User.handle.ilike(f"%{term}%")
                    | User.display_name.ilike(f"%{term}%"),
                )
                .order_by(User.username)
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    if not found:
        return []

    existing = (
        (
            await db.execute(
                select(Friendship).where(
                    or_(Friendship.requester_id == user.id, Friendship.addressee_id == user.id)
                )
            )
        )
        .scalars()
        .all()
    )
    relations: dict[uuid.UUID, str] = {}
    for row in existing:
        other = row.addressee_id if row.requester_id == user.id else row.requester_id
        if row.status == "accepted":
            relations[other] = "friends"
        else:
            relations[other] = "pending_out" if row.requester_id == user.id else "pending_in"
    return [_person(u, relations.get(u.id, "none")) for u in found]


async def _by_username(db: AsyncSession, user: User, username: str) -> User:
    other = (
        await db.execute(
            select(User).where(
                func.lower(User.username) == username.strip().lower(),
                User.tenant_id == user.tenant_id,
                User.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if other is None:
        raise HTTPException(status_code=404, detail="no account with that name")
    if other.id == user.id:
        raise HTTPException(status_code=400, detail="that is you")
    return other


class RequestBody(BaseModel):
    username: str


@router.post("/friends/request", status_code=201, dependencies=[Depends(csrf_protect)])
async def send_request(
    body: RequestBody,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    other = await _by_username(db, user, body.username)
    existing = (
        await db.execute(
            select(Friendship).where(
                or_(
                    (Friendship.requester_id == user.id) & (Friendship.addressee_id == other.id),
                    (Friendship.requester_id == other.id) & (Friendship.addressee_id == user.id),
                )
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        if existing.status == "accepted":
            return {"status": "friends"}
        # They already asked you. Asking back is the same as saying yes,
        # which is what someone pressing the button means.
        if existing.addressee_id == user.id:
            existing.status = "accepted"
            existing.responded_at = datetime.now(UTC)
            await db.commit()
            return {"status": "friends"}
        return {"status": "pending"}

    db.add(Friendship(requester_id=user.id, addressee_id=other.id, status="pending"))
    await notifications.notify(
        db,
        other,
        "friend_request",
        f"{user.username} wants to be friends",
        payload={"username": user.username},
        push_title="Friend request",
    )
    await audit(db, "friend.request", actor=user, request=request, detail={"to": other.username})
    await db.commit()
    return {"status": "pending"}


@router.post("/friends/{username}/accept", dependencies=[Depends(csrf_protect)])
async def accept_request(
    username: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    other = await _by_username(db, user, username)
    row = (
        await db.execute(
            select(Friendship).where(
                Friendship.requester_id == other.id,
                Friendship.addressee_id == user.id,
                Friendship.status == "pending",
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="no request from that person")
    row.status = "accepted"
    row.responded_at = datetime.now(UTC)
    await notifications.notify(
        db,
        other,
        "friend_request",
        f"{user.username} accepted your friend request",
        payload={"username": user.username},
        push_title="Friends now",
    )
    await audit(db, "friend.accept", actor=user, request=request, detail={"with": other.username})
    await db.commit()
    return {"status": "friends"}


@router.delete("/friends/{username}", status_code=204, dependencies=[Depends(csrf_protect)])
async def remove_friend(
    username: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Declines a request, cancels one you sent, or unfriends. All three are
    the same thing: the row goes away, and either side can ask again."""
    other = await _by_username(db, user, username)
    row = (
        await db.execute(
            select(Friendship).where(
                or_(
                    (Friendship.requester_id == user.id) & (Friendship.addressee_id == other.id),
                    (Friendship.requester_id == other.id) & (Friendship.addressee_id == user.id),
                )
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="not connected to that person")
    await db.delete(row)
    await audit(db, "friend.remove", actor=user, request=request, detail={"with": other.username})
    await db.commit()
