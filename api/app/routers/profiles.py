"""Someone's profile, seen by someone else.

The whole file is a filter. What comes back depends entirely on whether the
viewer is allowed to see it, and on which parts of their stats the subject
chose to show. Anything not permitted is left out rather than sent as a
zero, so a hidden number and a real zero never look the same.
"""

import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth.deps import get_current_user
from app.db import get_db
from app.models import Comment, Friendship, List, ListItem, User, WatchEvent
from app.social import visibility

router = APIRouter(prefix="/api")

# Panels, their levels and who may see them live in app.social.visibility,
# because written things appear in the feed and under titles as well as here.
# Re-exported so the older import path keeps working.
STAT_PANELS = visibility.STAT_PANELS
DEFAULT_PANEL = visibility.DEFAULT
panel_level = visibility.panel_level
can_see_panel = visibility.can_see_panel


class ProfileTitle(BaseModel):
    tmdb_id: int
    type: str
    name: str
    poster_path: str | None
    year: int | None


class ProfileList(BaseModel):
    id: str
    name: str
    kind: str
    count: int


class ProfileOut(BaseModel):
    handle: str | None
    username: str
    display_name: str | None
    avatar_path: str | None
    visibility: str
    # Your own profile, so the page can offer editing rather than following.
    yours: bool
    friend_status: str | None = None
    joined: datetime | None = None
    # Every field below is absent when the viewer may not see that panel.
    watched: int | None = None
    hours: float | None = None
    loved: int | None = None
    genres: list[dict] | None = None
    favourites: list[ProfileTitle] | None = None
    lists: list[ProfileList] | None = None
    # The one line they put above their name, with the film it is from.
    featured_line: dict | None = None
    # The same year grid the owner sees on their own stats page, so a
    # profile is a real page rather than three numbers.
    days: list[dict] | None = None
    years: list[int] | None = None
    streak: int | None = None
    avg_rating: float | None = None
    # Which panels were withheld, so the page can say so plainly instead of
    # looking broken.
    hidden: list[str] = []


@router.get("/profiles/{handle}", response_model=ProfileOut)
async def get_profile(
    handle: str,
    viewer: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileOut:
    subject = (
        await db.execute(
            select(User).where(
                func.lower(User.handle) == handle.lower().lstrip("@"),
                User.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if subject is None:
        raise HTTPException(status_code=404, detail="no one by that name")

    yours = subject.id == viewer.id
    friend_status = None
    if not yours:
        link = (
            await db.execute(
                select(Friendship).where(
                    (
                        (Friendship.requester_id == viewer.id)
                        & (Friendship.addressee_id == subject.id)
                    )
                    | (
                        (Friendship.requester_id == subject.id)
                        & (Friendship.addressee_id == viewer.id)
                    )
                )
            )
        ).scalar_one_or_none()
        friend_status = link.status if link else None

    out = ProfileOut(
        handle=subject.handle,
        username=subject.username,
        display_name=subject.display_name,
        avatar_path=subject.avatar_path,
        visibility=subject.visibility,
        yours=yours,
        friend_status=friend_status,
        joined=subject.created_at,
    )
    hidden: list[str] = []

    if await can_see_panel(db, viewer, subject, "numbers"):
        rows = (
            (
                await db.execute(
                    select(WatchEvent)
                    .options(joinedload(WatchEvent.title))
                    .where(WatchEvent.user_id == subject.id)
                )
            )
            .scalars()
            .all()
        )
        out.watched = len(rows)
        out.hours = round(sum((e.title.runtime or 0) for e in rows) / 60, 1)
        out.loved = sum(1 for e in rows if e.loved)

        rated = [e for e in rows if e.rating_10 is not None]
        out.avg_rating = (
            round(sum(e.rating_10 or 0 for e in rated) / len(rated), 1) if rated else None
        )

        # One entry per day that has something, each carrying a little
        # artwork, matching the shape the owner's own grid already reads.
        from collections import Counter

        per_day: Counter[str] = Counter()
        art: dict[str, list[dict]] = {}
        seen_years: set[int] = set()
        for event in rows:
            watched = event.watched_at
            if watched.tzinfo is None:
                watched = watched.replace(tzinfo=UTC)
            key = watched.date().isoformat()
            per_day[key] += 1
            seen_years.add(watched.year)
            bucket = art.setdefault(key, [])
            if len(bucket) < 12:
                bucket.append(
                    {
                        "tmdb_id": event.title.tmdb_id,
                        "type": event.title.type,
                        "name": event.title.name,
                        "poster_path": event.title.poster_path,
                        "year": event.title.year,
                        "rating_10": event.rating_10,
                        "loved": event.loved,
                    }
                )
        out.days = [
            {
                "day": day,
                "count": count,
                "names": [t["name"] for t in art.get(day, [])[:6]],
                "titles": art.get(day, []),
            }
            for day, count in sorted(per_day.items())
        ]
        out.years = sorted(seen_years, reverse=True)

        # Longest run of consecutive days, same rule as the stats page.
        longest = 0
        run = 0
        previous = None
        for day in sorted(per_day):
            current = date.fromisoformat(day)
            run = run + 1 if previous is not None and (current - previous).days == 1 else 1
            longest = max(longest, run)
            previous = current
        out.streak = longest
    else:
        hidden.append("numbers")

    if await can_see_panel(db, viewer, subject, "genres"):
        from collections import Counter

        counter: Counter[str] = Counter()
        rows = (
            (
                await db.execute(
                    select(WatchEvent)
                    .options(joinedload(WatchEvent.title))
                    .where(WatchEvent.user_id == subject.id)
                )
            )
            .scalars()
            .all()
        )
        for event in rows:
            for genre in event.title.genres or []:
                if genre.get("name"):
                    counter[genre["name"]] += 1
        out.genres = [{"name": n, "count": c} for n, c in counter.most_common(6)]
    else:
        hidden.append("genres")

    if await can_see_panel(db, viewer, subject, "favourites"):
        events = (
            (
                await db.execute(
                    select(WatchEvent)
                    .options(joinedload(WatchEvent.title))
                    .where(WatchEvent.user_id == subject.id)
                    .order_by(
                        WatchEvent.loved.desc(),
                        WatchEvent.rating_10.desc().nulls_last(),
                    )
                    .limit(48)
                )
            )
            .scalars()
            .all()
        )
        # A rewatch is two events but one favourite: the grid shows titles,
        # so the same one must never appear twice however often it was seen.
        seen_titles: set[uuid.UUID] = set()
        loved: list[WatchEvent] = []
        for event in events:
            if event.title_id in seen_titles:
                continue
            seen_titles.add(event.title_id)
            loved.append(event)
            if len(loved) == 12:
                break
        out.favourites = [
            ProfileTitle(
                tmdb_id=e.title.tmdb_id,
                type=e.title.type,
                name=e.title.name,
                poster_path=e.title.poster_path,
                year=e.title.year,
            )
            for e in loved
        ]
    else:
        hidden.append("favourites")

    if await can_see_panel(db, viewer, subject, "lists"):
        listings = (
            (
                await db.execute(
                    select(List).where(List.user_id == subject.id, List.kind != "cinema")
                )
            )
            .scalars()
            .all()
        )
        out.lists = []
        for listing in listings:
            count = (
                await db.execute(
                    select(func.count(ListItem.id)).where(ListItem.list_id == listing.id)
                )
            ).scalar_one()
            out.lists.append(
                ProfileList(id=str(listing.id), name=listing.name, kind=listing.kind, count=count)
            )
    else:
        hidden.append("lists")

    # One line, at the top, rather than an inventory of everything they ever
    # saved. A list of saved lines is a collection; the one they chose to put
    # above their name is a statement about them, and that is what people
    # were reaching for.
    if subject.featured_quote_id and await can_see_panel(db, viewer, subject, "posts"):
        from app.models import Quote

        line = (
            await db.execute(
                select(Quote)
                .options(joinedload(Quote.title))
                .where(Quote.id == subject.featured_quote_id)
            )
        ).scalar_one_or_none()
        if line is not None:
            out.featured_line = {
                "id": str(line.id),
                "body": line.body,
                "character": line.character,
                "title": {
                    "tmdb_id": line.title.tmdb_id,
                    "type": line.title.type,
                    "name": line.title.name,
                    # The cover is the width of the page, so it needs the
                    # backdrop rather than the poster. Poster is the fallback
                    # for the handful of titles with no backdrop at all.
                    "backdrop_path": line.title.backdrop_path,
                    "poster_path": line.title.poster_path,
                    "year": line.title.year,
                },
            }

    out.hidden = hidden
    await db.commit()
    return out


@router.get("/profiles/{handle}/posts")
async def profile_posts(
    handle: str,
    viewer: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """What this person has written, subject to their posts panel."""
    from app.routers.comments import _like_state, _out

    subject = (
        await db.execute(
            select(User).where(
                func.lower(User.handle) == handle.lower().lstrip("@"),
                User.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if subject is None:
        raise HTTPException(status_code=404, detail="no one by that name")
    if not await can_see_panel(db, viewer, subject, "posts"):
        return {"total": 0, "comments": [], "hidden": True}

    total = (
        await db.execute(select(func.count(Comment.id)).where(Comment.user_id == subject.id))
    ).scalar_one()
    rows = (
        (
            await db.execute(
                select(Comment)
                .options(
                    joinedload(Comment.user),
                    joinedload(Comment.title),
                    joinedload(Comment.shared).joinedload(Comment.user),
                    joinedload(Comment.shared).joinedload(Comment.title),
                )
                .where(Comment.user_id == subject.id)
                .order_by(Comment.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    counts, liked = await _like_state(db, viewer, [c.id for c in rows])
    # Seeing this person's posts does not mean seeing whoever they reshared.
    allowed = await visibility.visible_user_ids_for_panel(db, viewer, "posts")
    await db.commit()
    return {
        "total": total,
        "comments": [
            _out(c, viewer, counts, liked, allowed, with_title=True).model_dump() for c in rows
        ],
        "hidden": False,
    }


class Directory(BaseModel):
    handle: str | None
    username: str
    display_name: str | None
    avatar_path: str | None


@router.get("/profiles", response_model=list[Directory])
async def find_people(
    q: str = Query(min_length=1, max_length=40),
    viewer: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Directory]:
    """Look someone up by handle or name.

    Private accounts are still findable, because a handle has to be
    reachable for a friend request to be possible at all. What they are
    hiding is their things, not their existence."""
    term = f"%{q.strip().lstrip('@').lower()}%"
    rows = (
        (
            await db.execute(
                select(User)
                .where(
                    User.is_active.is_(True),
                    User.id != viewer.id,
                    func.lower(User.handle).like(term)
                    | func.lower(User.display_name).like(term)
                    | func.lower(User.username).like(term),
                )
                .limit(15)
            )
        )
        .scalars()
        .all()
    )
    return [
        Directory(
            handle=u.handle,
            username=u.username,
            display_name=u.display_name,
            avatar_path=u.avatar_path,
        )
        for u in rows
    ]
