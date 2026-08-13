"""Franchises and people: the two ways a viewer follows a thread out of one
title into everything connected to it."""

import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import audit
from app.auth.deps import csrf_protect, get_current_user
from app.catalog import ingest, tmdb
from app.catalog import watch_order as resolver  # aliased: a route below owns the plain name
from app.countries import for_user as countries_for
from app.db import get_db
from app.models import Availability, FollowedPerson, List, ListItem, Title, User
from app.routers.catalog import HomeRow, TitleCard, _attach_match_scores, _card_from_tmdb
from app.tracking import service as lists_service

router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])


class CollectionOut(BaseModel):
    id: int
    name: str
    overview: str | None
    poster_path: str | None
    backdrop_path: str | None
    parts: list[TitleCard]
    # How many of these the person has already seen or saved.
    watched_count: int
    in_list_count: int
    # The lowest number of times any part has been watched. Marking the
    # whole franchise tops every part up to one more than this, so the
    # button always means "and one more round" rather than "add one to
    # each", which would double count whatever you had already logged.
    times_all_watched: int = 0


@router.get("/collections/{collection_id}", response_model=CollectionOut)
async def get_collection(
    collection_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CollectionOut:
    try:
        payload = await tmdb.collection(db, collection_id)
    except tmdb.TmdbNotConfigured as exc:
        raise HTTPException(status_code=503, detail="tmdb_not_configured") from exc
    except tmdb.TmdbError as exc:
        raise HTTPException(status_code=502, detail="tmdb_unavailable") from exc

    parts = [
        card
        for card in (_card_from_tmdb(item, "movie") for item in payload.get("parts", []))
        if card is not None
    ]
    # Release order, by date rather than year. Sorting by year looks right
    # until a franchise ships four films in one of them, and then the order
    # within that year is whatever TMDB happened to return.
    parts.sort(key=lambda card: (card.release_date is None, card.release_date or date.max))

    tmdb_ids = [card.tmdb_id for card in parts]
    known = {
        t.tmdb_id: t
        for t in (await db.execute(select(Title).where(Title.tmdb_id.in_(tmdb_ids)))).scalars()
    }
    from app.models import WatchEvent

    watched_ids = set(
        (
            await db.execute(select(WatchEvent.title_id).where(WatchEvent.user_id == user.id))
        ).scalars()
    )
    listed_ids = set(
        (
            await db.execute(
                select(ListItem.title_id)
                .join(List, List.id == ListItem.list_id)
                .where((List.user_id == user.id) | (List.kind == "shared"))
            )
        ).scalars()
    )

    # How many complete times through: the smallest per part count, so one
    # unwatched part means zero rounds however often the others were seen.
    count_rows = (
        await db.execute(
            select(WatchEvent.title_id, func.count(WatchEvent.id))
            .where(
                WatchEvent.user_id == user.id,
                WatchEvent.title_id.in_([t.id for t in known.values()]),
            )
            .group_by(WatchEvent.title_id)
        )
    ).all()
    counts: dict[uuid.UUID, int] = {row[0]: row[1] for row in count_rows}
    per_part = [
        counts.get(t.id, 0) if (t := known.get(c.tmdb_id)) is not None else 0 for c in parts
    ]
    rounds = min(per_part) if per_part else 0

    rows = [HomeRow(key="parts", title=payload.get("name", "Franchise"), items=parts)]
    await _attach_match_scores(db, user, rows)
    await db.commit()

    return CollectionOut(
        id=collection_id,
        name=payload.get("name", "Franchise"),
        overview=payload.get("overview") or None,
        poster_path=payload.get("poster_path"),
        backdrop_path=payload.get("backdrop_path"),
        parts=rows[0].items,
        watched_count=sum(1 for c in parts if (t := known.get(c.tmdb_id)) and t.id in watched_ids),
        in_list_count=sum(1 for c in parts if (t := known.get(c.tmdb_id)) and t.id in listed_ids),
        times_all_watched=rounds,
    )


class WatchAllBody(BaseModel):
    # The number of viewings every part should end up with. Not an
    # increment: the whole point is that a part already logged once is left
    # alone when the target is one.
    times: int = Field(default=1, ge=1, le=20)


class WatchAllResult(BaseModel):
    # Viewings actually written, parts that were already at the target, and
    # parts not in the catalog yet.
    logged: int
    already_counted: int
    skipped: int
    times: int


@router.post(
    "/collections/{collection_id}/watched",
    response_model=WatchAllResult,
    dependencies=[Depends(csrf_protect)],
)
async def mark_collection_watched(
    collection_id: int,
    body: WatchAllBody,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WatchAllResult:
    """Mark a whole franchise as seen, without double counting.

    Saying you have seen all of a franchise is not the same as saying you
    watched each part one more time. Parts you already logged stay as they
    are; only the ones behind get topped up. Pressing it again with times=2
    is how you say you have been round the whole thing twice."""
    from datetime import UTC, datetime

    from app.models import WatchEvent

    try:
        payload = await tmdb.collection(db, collection_id)
    except tmdb.TmdbNotConfigured as exc:
        raise HTTPException(status_code=503, detail="tmdb_not_configured") from exc
    except tmdb.TmdbError as exc:
        raise HTTPException(status_code=502, detail="tmdb_unavailable") from exc

    logged = 0
    already = 0
    skipped = 0
    now = datetime.now(UTC)

    for item in payload.get("parts", []):
        tmdb_id = item.get("id")
        if not tmdb_id:
            skipped += 1
            continue
        try:
            title = await ingest.ensure_title(db, "movie", int(tmdb_id))
        except (tmdb.TmdbError, tmdb.TmdbNotConfigured):
            # One part missing upstream must not lose the rest of the run.
            skipped += 1
            continue
        if title is None:
            skipped += 1
            continue

        seen = (
            await db.execute(
                select(func.count(WatchEvent.id)).where(
                    WatchEvent.user_id == user.id, WatchEvent.title_id == title.id
                )
            )
        ).scalar_one()
        missing = body.times - int(seen)
        if missing <= 0:
            already += 1
            continue
        for _ in range(missing):
            db.add(WatchEvent(user_id=user.id, title_id=title.id, watched_at=now))
            logged += 1

    if logged:
        from app.ai import taste as taste_module

        await taste_module.invalidate_taste(db, user)
    await audit(
        db,
        "collection.watched",
        actor=user,
        request=request,
        object_type="collection",
        object_id=str(collection_id),
        detail={"times": body.times, "logged": logged},
    )
    await db.commit()
    return WatchAllResult(logged=logged, already_counted=already, skipped=skipped, times=body.times)


class BulkAddBody(BaseModel):
    # As many as a watch order can contain, not a number of its own. The
    # franchise resolver is the biggest caller here and a cap below what it
    # can produce makes its own proposals unsaveable.
    titles: list[dict] = Field(min_length=1, max_length=resolver.MAX_TITLES)
    shared: bool = False
    # Save into a named list of their own rather than the watchlist. This is
    # what a franchise or an assistant proposal wants: "Marvel, in order" is
    # a different thing from the general pile of what to watch next.
    name: str | None = Field(default=None, max_length=120)


class BulkAddResult(BaseModel):
    added: int
    already_there: int
    failed: int
    list_name: str


@router.post("/lists/bulk", response_model=BulkAddResult, dependencies=[Depends(csrf_protect)])
async def bulk_add(
    body: BulkAddBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BulkAddResult:
    """Save a whole franchise, or a proposed set, in one go.

    Order is preserved. The titles arrive in the order they should be
    watched, and each gets a position, because a list of eight films that
    renders newest-first is not a watch-through.

    What we already hold is read in one query rather than one call each.
    ensure_title refreshes anything older than a day, so routing every entry
    through it turned a save into a full refresh of the franchise: of the
    seventy-two titles in the Marvel universe, seventy were already in the
    catalog and sixty-four of those were stale. Sixty-four sequential TMDB
    calls, to write rows that needed no network at all. A save is a save; if
    the catalog is a day out of date, that is not this button's problem.
    """
    if body.name:
        target = await lists_service.ensure_named_list(db, user, body.name)
    elif body.shared:
        target = await lists_service.ensure_shared_list(db, user)
    else:
        target = await lists_service.ensure_watchlist(db, user)
    existing = set(
        (await db.execute(select(ListItem.title_id).where(ListItem.list_id == target.id))).scalars()
    )

    # Continue from wherever the list already ends, so adding a second
    # franchise does not interleave with the first.
    highest = (
        await db.execute(select(func.max(ListItem.position)).where(ListItem.list_id == target.id))
    ).scalar_one_or_none()
    position = (highest or 0) + 1

    # Everything we already have, in one round trip. Keyed by type as well
    # as id because a film and a series can share a TMDB id.
    wanted = [
        entry["tmdb_id"]
        for entry in body.titles
        if entry.get("type") in ("movie", "tv") and isinstance(entry.get("tmdb_id"), int)
    ]
    known: dict[tuple[str, int], Title] = {}
    if wanted:
        rows = (await db.execute(select(Title).where(Title.tmdb_id.in_(wanted)))).scalars().all()
        known = {(row.type, row.tmdb_id): row for row in rows}

    added = already = failed = 0
    for entry in body.titles:
        media_type = entry.get("type")
        tmdb_id = entry.get("tmdb_id")
        if media_type not in ("movie", "tv") or not isinstance(tmdb_id, int):
            failed += 1
            continue
        title = known.get((media_type, tmdb_id))
        if title is None:
            # Only what we have never seen costs a fetch.
            try:
                title = await ingest.ensure_title(db, media_type, tmdb_id)
            except (tmdb.TmdbError, tmdb.TmdbNotConfigured):
                failed += 1
                continue
            known[(media_type, tmdb_id)] = title
        if title.id in existing:
            already += 1
            continue
        await lists_service.add_title_to_list(db, target, title.id, user, position=position)
        existing.add(title.id)
        position += 1
        added += 1

    await audit(
        db,
        "list.bulk_add",
        actor=user,
        object_type="list",
        object_id=str(target.id),
        detail={"added": added, "already_there": already, "failed": failed},
    )
    await db.commit()
    return BulkAddResult(added=added, already_there=already, failed=failed, list_name=target.name)


class PersonCredit(BaseModel):
    tmdb_id: int
    type: str
    name: str
    poster_path: str | None
    year: int | None
    character: str | None
    job: str | None


class PersonOut(BaseModel):
    id: int
    name: str
    biography: str | None
    birthday: str | None
    deathday: str | None
    place_of_birth: str | None
    profile_path: str | None
    known_for_department: str | None
    imdb_id: str | None
    acting: list[PersonCredit]
    crew: list[PersonCredit]


# Talk shows, news and reality: appearances as themselves, not work worth
# listing under an actor's name.
APPEARANCE_GENRES = {10767, 10763, 10764}


def _credit(item: dict) -> PersonCredit | None:
    media_type = item.get("media_type")
    if media_type not in ("movie", "tv"):
        return None
    if APPEARANCE_GENRES & set(item.get("genre_ids") or []):
        return None
    if (item.get("character") or "").strip().lower() in ("self", "himself", "herself"):
        return None
    date = item.get("release_date") if media_type == "movie" else item.get("first_air_date")
    return PersonCredit(
        tmdb_id=item["id"],
        type=media_type,
        name=item.get("title") or item.get("name") or "Untitled",
        poster_path=item.get("poster_path"),
        year=int(date[:4]) if date and date[:4].isdigit() else None,
        character=item.get("character") or None,
        job=item.get("job") or None,
    )


@router.get("/people/{person_id}", response_model=PersonOut)
async def get_person(
    person_id: int,
    db: AsyncSession = Depends(get_db),
) -> PersonOut:
    try:
        payload = await tmdb.person(db, person_id)
    except tmdb.TmdbNotConfigured as exc:
        raise HTTPException(status_code=503, detail="tmdb_not_configured") from exc
    except tmdb.TmdbError as exc:
        raise HTTPException(status_code=502, detail="tmdb_unavailable") from exc
    await db.commit()

    credits = payload.get("combined_credits") or {}

    def ordered(items: list[dict], limit: int) -> list[PersonCredit]:
        # Most recognised work first, which is what people came to see.
        ranked = sorted(items, key=lambda i: -(i.get("popularity") or 0))
        out: list[PersonCredit] = []
        seen: set[tuple[str, int]] = set()
        for item in ranked:
            credit = _credit(item)
            if credit is None or not credit.poster_path:
                continue
            key = (credit.type, credit.tmdb_id)
            if key in seen:
                continue
            seen.add(key)
            out.append(credit)
            if len(out) >= limit:
                break
        return out

    return PersonOut(
        id=person_id,
        name=payload.get("name", "Unknown"),
        biography=payload.get("biography") or None,
        birthday=payload.get("birthday"),
        deathday=payload.get("deathday"),
        place_of_birth=payload.get("place_of_birth"),
        profile_path=payload.get("profile_path"),
        known_for_department=payload.get("known_for_department"),
        imdb_id=(payload.get("external_ids") or {}).get("imdb_id"),
        acting=ordered(credits.get("cast") or [], 24),
        crew=ordered(credits.get("crew") or [], 12),
    )


def _watchable_at_home(part: dict, known: dict, at_home: set) -> bool:
    """Whether this part can be watched at home today.

    Unreleased is the easy half. The harder half is a film that has come out
    but is still only in cinemas: it has a release date in the past and no
    listing on anything, so the absence of availability is the signal."""
    released = str(part.get("release_date") or "")[:10]
    if not released:
        return False  # no date at all: not something to suggest tonight
    if released > datetime.now(UTC).date().isoformat():
        return False
    local = known.get(part.get("id"))
    if local is None:
        # Not in the catalog yet, so nothing is known about where it plays.
        # Staying quiet beats recommending something unwatchable.
        return False
    return local.id in at_home


class NextUp(BaseModel):
    title: TitleCard
    collection_name: str
    # So the card can act on the whole franchise, not just the next part.
    collection_id: int
    reason: str
    remaining: int


@router.get("/next-up", response_model=list[NextUp])
async def next_up(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[NextUp]:
    """Franchises this person started and has not finished.

    Finishing one part of a series is the clearest signal there is about
    what to watch next, so it is answered directly rather than left to
    similarity."""
    from app.models import Interaction, WatchEvent

    # Everything they have engaged with positively, newest first.
    watched = (
        await db.execute(
            select(Title, WatchEvent.watched_at)
            .join(WatchEvent, WatchEvent.title_id == Title.id)
            .where(WatchEvent.user_id == user.id, Title.collection_id.is_not(None))
            .order_by(WatchEvent.watched_at.desc())
        )
    ).all()
    liked = (
        await db.execute(
            select(Title, Interaction.created_at)
            .join(Interaction, Interaction.title_id == Title.id)
            .where(
                Interaction.user_id == user.id,
                Interaction.kind == "like",
                Title.collection_id.is_not(None),
            )
            .order_by(Interaction.created_at.desc())
        )
    ).all()

    seen_ids = set(
        (
            await db.execute(select(WatchEvent.title_id).where(WatchEvent.user_id == user.id))
        ).scalars()
    )
    disliked_ids = set(
        (
            await db.execute(
                select(Interaction.title_id).where(
                    Interaction.user_id == user.id, Interaction.kind == "dislike"
                )
            )
        ).scalars()
    )

    ordered = sorted(
        [(when, title, "watched") for title, when in watched]
        + [(when, title, "liked") for title, when in liked],
        key=lambda row: row[0],
        reverse=True,
    )

    # Everything the person can start at home right now: anything with a
    # streaming, rental, purchase, free or ad-supported listing in one of
    # their countries. Loaded once rather than per part.
    countries = countries_for(user)
    at_home: set[uuid.UUID] = set()
    if countries:
        at_home = set(
            (
                await db.execute(
                    select(Availability.title_id).where(Availability.country.in_(countries))
                )
            )
            .scalars()
            .all()
        )

    out: list[NextUp] = []
    handled: set[int] = set()
    for _, anchor, verb in ordered:
        if anchor.collection_id in handled or len(out) >= 6:
            continue
        handled.add(anchor.collection_id)
        try:
            payload = await tmdb.collection(db, anchor.collection_id)
        except (tmdb.TmdbNotConfigured, tmdb.TmdbError):
            continue

        parts = sorted(
            (p for p in payload.get("parts", []) if p.get("poster_path")),
            key=lambda p: p.get("release_date") or "9999",
        )
        known = {
            t.tmdb_id: t
            for t in (
                await db.execute(select(Title).where(Title.tmdb_id.in_([p["id"] for p in parts])))
            ).scalars()
        }
        # The first part they have not seen and have not rejected.
        remaining = [
            p
            for p in parts
            if (local := known.get(p["id"])) is None
            or (local.id not in seen_ids and local.id not in disliked_ids)
        ]
        # And that they could actually watch tonight. Suggesting a film that
        # is unreleased, or only playing in cinemas, is not a suggestion: it
        # is a thing to be annoyed about. The cinema page is where those
        # belong.
        remaining = [p for p in remaining if _watchable_at_home(p, known, at_home)]
        if not remaining:
            continue
        card = _card_from_tmdb(remaining[0], "movie")
        if card is None:
            continue
        out.append(
            NextUp(
                title=card,
                collection_name=payload.get("name", "this franchise"),
                collection_id=int(payload.get("id") or anchor.collection_id),
                reason=f"You {verb} {anchor.name}",
                remaining=len(remaining),
            )
        )

    if out:
        rows = [HomeRow(key="next-up", title="Next up", items=[n.title for n in out])]
        await _attach_match_scores(db, user, rows)
        for entry, card in zip(out, rows[0].items, strict=True):
            entry.title = card
    await db.commit()
    return out


class FollowedOut(BaseModel):
    person_id: int
    name: str
    profile_path: str | None


@router.get("/following", response_model=list[FollowedOut])
async def following(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[FollowedOut]:
    rows = (
        (
            await db.execute(
                select(FollowedPerson)
                .where(FollowedPerson.user_id == user.id)
                .order_by(FollowedPerson.name)
            )
        )
        .scalars()
        .all()
    )
    return [
        FollowedOut(person_id=r.person_id, name=r.name, profile_path=r.profile_path) for r in rows
    ]


@router.post("/people/{person_id}/follow", dependencies=[Depends(csrf_protect)])
async def follow_person(
    person_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Following someone is a strong signal, so it also counts toward what
    gets suggested, not just what raises an alert."""
    existing = (
        await db.execute(
            select(FollowedPerson).where(
                FollowedPerson.user_id == user.id, FollowedPerson.person_id == person_id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {"following": True}

    name, profile_path, latest = f"Person {person_id}", None, None
    try:
        payload = await tmdb.person(db, person_id)
        name = payload.get("name") or name
        profile_path = payload.get("profile_path")
        credits = (payload.get("combined_credits") or {}).get("cast") or []
        years = [
            int(str(c.get("release_date") or c.get("first_air_date") or "")[:4])
            for c in credits
            if str(c.get("release_date") or c.get("first_air_date") or "")[:4].isdigit()
        ]
        latest = max(years) if years else None
    except (tmdb.TmdbNotConfigured, tmdb.TmdbError):
        # Following still works offline; the name fills in on the next view.
        pass

    db.add(
        FollowedPerson(
            user_id=user.id,
            person_id=person_id,
            name=name,
            profile_path=profile_path,
            last_seen_credit=latest,
        )
    )
    await db.commit()
    return {"following": True}


@router.delete("/people/{person_id}/follow", status_code=204, dependencies=[Depends(csrf_protect)])
async def unfollow_person(
    person_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    row = (
        await db.execute(
            select(FollowedPerson).where(
                FollowedPerson.user_id == user.id, FollowedPerson.person_id == person_id
            )
        )
    ).scalar_one_or_none()
    if row is not None:
        await db.delete(row)
        await db.commit()


class WatchOrderTitle(BaseModel):
    tmdb_id: int
    type: str
    name: str
    year: int | None
    release_date: date | None
    poster_path: str | None
    overview: str | None
    watched: bool


class WatchOrderOut(BaseModel):
    name: str
    # universe | collection | anchor
    kind: str
    titles: list[WatchOrderTitle]
    watched: int
    total: int
    note: str = ""


@router.get("/watch-order", response_model=WatchOrderOut)
async def watch_order(
    q: str | None = None,
    tmdb_id: int | None = None,
    type: str = "movie",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WatchOrderOut:
    """A franchise, in the order you would watch it, with what you have seen.

    Deterministic. Given "marvel" or "harry potter" this is the whole answer,
    with no model involved, which is why it also works on an instance with
    the assistant switched off. The assistant calls the same endpoint and
    writes a sentence around the result rather than producing the list.
    """
    if not q and tmdb_id is None:
        raise HTTPException(status_code=422, detail="ask for a franchise by name or by title")

    try:
        found = await resolver.resolve(db, query=q, tmdb_id=tmdb_id, media_type=type, user=user)
    except tmdb.TmdbNotConfigured as exc:
        raise HTTPException(status_code=503, detail="tmdb_not_configured") from exc
    except tmdb.TmdbError as exc:
        raise HTTPException(status_code=502, detail="tmdb_unavailable") from exc
    await db.commit()

    if found is None:
        raise HTTPException(status_code=404, detail="no franchise by that name")

    return WatchOrderOut(
        name=found.name,
        kind=found.kind,
        titles=[
            WatchOrderTitle(
                tmdb_id=t.tmdb_id,
                type=t.type,
                name=t.name,
                year=t.year,
                release_date=t.release_date,
                poster_path=t.poster_path,
                overview=t.overview,
                watched=t.watched,
            )
            for t in found.titles
        ],
        watched=sum(1 for t in found.titles if t.watched),
        total=len(found.titles),
        note=found.note,
    )
