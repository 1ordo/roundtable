"""The cinema tracker.

Some films are worth leaving the house for, and the window to do it is
short. This tracks the ones someone wants to see on a big screen and tells
them when it opens near them, while there is still time to book.

Everything is per country, because a release date is not a global fact: a
film opening this week in one place may be three months away in another.
"""

import contextlib
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import csrf_protect, get_current_user
from app.catalog import ingest, tmdb
from app.countries import for_user as countries_for
from app.db import get_db
from app.models import List, ListItem, Title, User
from app.routers.catalog import TitleCard, _card_from_title, _card_from_tmdb

router = APIRouter(prefix="/api")

# TMDB release types. 3 is a proper theatrical run; 2 is a limited one.
THEATRICAL = (2, 3)
CINEMA_LIST = "cinema"
# How long a film stays "in cinemas" for the purpose of an alert. Runs vary,
# but past this the chance of catching it has usually gone.
RUN_WEEKS = 8
# How far ahead of the local release date to say something. A week is enough
# notice to make a plan with someone and still close enough that the film is
# actually bookable, which the morning of the release is not.
LEAD_DAYS = 7
# How deep to page each list. Twenty per page, so this is up to a hundred
# films on either side, which is more than any one city is showing.
PAGES = 5


class CinemaTitle(BaseModel):
    card: TitleCard
    # The theatrical date in this person's country, when it is known.
    opens_on: date | None = None
    in_cinemas_now: bool = False
    tracked: bool = False
    # Which of their countries this listing came from, so a page covering
    # several does not blur them together.
    country: str | None = None


class CinemaPage(BaseModel):
    # The main one, plus every other country being covered.
    country: str | None
    countries: list[str] = []
    now_showing: list[CinemaTitle]
    coming_soon: list[CinemaTitle]
    # The ones this person said they want to see on a big screen.
    tracking: list[CinemaTitle]
    # Kept so older clients do not break on a missing field. Always empty:
    # this page shows only what has a date in a country you set.
    elsewhere: list[CinemaTitle] = []


def theatrical_date(payload: dict, country: str | None) -> date | None:
    """When a film opens in cinemas in one country.

    Falls back to nothing rather than to another country's date: a date
    from the wrong place is worse than no date, because someone will plan
    around it."""
    if not country:
        return None
    for entry in (payload.get("release_dates") or {}).get("results", []):
        if entry.get("iso_3166_1") != country:
            continue
        dates = []
        for release in entry.get("release_dates", []):
            if release.get("type") not in THEATRICAL:
                continue
            text = str(release.get("release_date") or "")[:10]
            try:
                dates.append(date.fromisoformat(text))
            except ValueError:
                continue
        if dates:
            return min(dates)
    return None


def is_showing(opens: date | None, today: date | None = None) -> bool:
    """Whether a film is probably in cinemas right now."""
    if opens is None:
        return False
    today = today or datetime.now(UTC).date()
    return opens <= today <= opens + timedelta(weeks=RUN_WEEKS)


def alert_due(opens: date | None, today: date | None = None, lead: int = LEAD_DAYS) -> bool:
    """Whether now is the moment to say something about a cinema release.

    The window opens a week before the local release date and stays open
    until the film leaves cinemas. The far edge matters as much as the near
    one: a film added to the list the day before it opens, or a week after,
    should still get its one alert rather than silently miss the window.
    Exactly-once is enforced by the caller, which checks for an existing
    cinema notification before sending.
    """
    if opens is None:
        return False
    today = today or datetime.now(UTC).date()
    return opens - timedelta(days=lead) <= today <= opens + timedelta(weeks=RUN_WEEKS)


async def _cinema_list(db: AsyncSession, user: User, create: bool = False) -> List | None:
    found = (
        await db.execute(
            select(List).where(
                List.tenant_id == user.tenant_id,
                List.user_id == user.id,
                List.kind == CINEMA_LIST,
            )
        )
    ).scalar_one_or_none()
    if found is None and create:
        found = List(
            tenant_id=user.tenant_id,
            user_id=user.id,
            name="See in a cinema",
            kind=CINEMA_LIST,
        )
        db.add(found)
        await db.flush()
    return found


async def tracked_titles(db: AsyncSession, user: User) -> list[Title]:
    listing = await _cinema_list(db, user)
    if listing is None:
        return []
    rows = (
        (
            await db.execute(
                select(Title)
                .join(ListItem, ListItem.title_id == Title.id)
                .where(ListItem.list_id == listing.id)
                .order_by(Title.year.desc().nulls_last(), Title.name)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


@router.get("/cinema", response_model=CinemaPage)
async def cinema(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> CinemaPage:
    """What is on, what is coming, and what you are waiting for."""
    wanted = countries_for(user)
    country = wanted[0] if wanted else None
    tracked = await tracked_titles(db, user)
    tracked_keys = {(t.type, t.tmdb_id) for t in tracked}

    now_showing: list[CinemaTitle] = []
    coming_soon: list[CinemaTitle] = []
    elsewhere: list[CinemaTitle] = []
    seen: set[int] = set()

    today = datetime.now(UTC).date()
    run_start = today - timedelta(weeks=RUN_WEEKS)
    horizon = today + timedelta(days=270)

    def add(bucket: list[CinemaTitle], item: dict, showing: bool, where: str | None = None) -> None:
        card = _card_from_tmdb(item, "movie")
        if card is None or card.tmdb_id in seen:
            return
        opens = None
        with contextlib.suppress(ValueError):
            opens = date.fromisoformat(str(item.get("release_date") or "")[:10])
        # Discover filters on the regional date but reports the film's
        # original one, so a re-release of a 1977 film comes back saying
        # 1977. Claiming "opens 1977" is worse than leaving it out, and
        # naming the real date would cost another call per film.
        if not showing and (opens is None or opens < today):
            return
        # "On now" means a current run, not a revival week. A film whose own
        # release date predates the window is a re-release, and mixing those
        # in with this month's releases is what makes the shelf look wrong.
        if showing and (opens is None or opens < run_start):
            return
        seen.add(card.tmdb_id)
        bucket.append(
            CinemaTitle(
                card=card,
                opens_on=opens,
                in_cinemas_now=showing,
                tracked=(card.type, card.tmdb_id) in tracked_keys,
                country=where,
            )
        )

    try:
        # Every country this person cares about, each labelled. Two sources
        # per country, merged: now_playing is TMDB's editorial list and
        # discover is the full theatrical index; neither alone is complete.
        for where in wanted:
            for page in range(1, PAGES + 1):
                payload = await tmdb.now_playing(db, where, page)
                for item in payload.get("results", []):
                    add(now_showing, item, True, where)
                if page >= payload.get("total_pages", 1):
                    break

            for page in range(1, PAGES + 1):
                payload = await tmdb.discover(
                    db,
                    "movie",
                    {
                        "region": where,
                        "with_release_type": "2|3",
                        "release_date.gte": run_start.isoformat(),
                        "release_date.lte": today.isoformat(),
                        "sort_by": "popularity.desc",
                        "page": page,
                    },
                )
                for item in payload.get("results", []):
                    add(now_showing, item, True, where)
                if page >= payload.get("total_pages", 1):
                    break

            for page in range(1, PAGES + 1):
                payload = await tmdb.discover(
                    db,
                    "movie",
                    {
                        "region": where,
                        "with_release_type": "2|3",
                        "release_date.gte": today.isoformat(),
                        "release_date.lte": horizon.isoformat(),
                        "sort_by": "popularity.desc",
                        "page": page,
                    },
                )
                for item in payload.get("results", []):
                    add(coming_soon, item, False, where)
                if page >= payload.get("total_pages", 1):
                    break

            for page in range(1, PAGES + 1):
                payload = await tmdb.upcoming(db, where, page)
                for item in payload.get("results", []):
                    add(coming_soon, item, False, where)
                if page >= payload.get("total_pages", 1):
                    break

        # There used to be a global fallback here: big films on release
        # anywhere, shown because per country theatrical dates are patchy.
        # It was removed on purpose. A cinema page that lists films playing
        # in another country is worse than a short one, because every entry
        # has to be checked before it can be trusted. What shows here now is
        # only what has a date in a country you set.

        # Soonest first: next week matters more than next year.
        coming_soon.sort(key=lambda c: (c.opens_on is None, c.opens_on or date.max))
    except (tmdb.TmdbNotConfigured, tmdb.TmdbError):
        # The tracked list still works without the upstream lists.
        pass

    tracking = []
    for title in tracked:
        # The soonest date across every country they follow: if it opens in
        # one of their places next week, that is the date that matters.
        dated: list[tuple[date, str]] = []
        for where in wanted:
            when = theatrical_date(title.raw_tmdb or {}, where)
            if when is not None:
                dated.append((when, where))
        opens: date | None = None
        opens_in: str | None = None
        if dated:
            opens, opens_in = min(dated)
        tracking.append(
            CinemaTitle(
                card=_card_from_title(title),
                opens_on=opens,
                in_cinemas_now=is_showing(opens),
                tracked=True,
                country=opens_in,
            )
        )
    # What is on is a short list, so it is not shelved: it is ordered.
    # Everything here carries a fit score, and what is showing now leads with
    # the best of it rather than with whatever is most popular globally.
    # Coming soon stays in date order, because a film that opens tomorrow is
    # more use than a better one that opens in March.
    await _attach_cinema_match(db, user, [now_showing, coming_soon, tracking, elsewhere])
    now_showing.sort(key=lambda c: -(c.card.match or 0))
    elsewhere.sort(key=lambda c: -(c.card.match or 0))

    await db.commit()
    return CinemaPage(
        country=country,
        countries=wanted,
        now_showing=now_showing,
        coming_soon=coming_soon,
        tracking=tracking,
        elsewhere=elsewhere,
    )


async def _attach_cinema_match(
    db: AsyncSession, user: User, groups: list[list[CinemaTitle]]
) -> None:
    """Stamp every listing with how well it fits this person.

    Cinema is the one place the personalized shelves deliberately cannot
    reach: a film only playing in cinemas is excluded from them by design.
    That makes this page the only answer to "which of these is for me", so
    the score has to be here."""
    from app.routers.catalog import HomeRow, _attach_match_scores

    # Wrapped in rows only because that is the shape the scorer takes; the
    # cards inside are the same objects the page returns, and it stamps them
    # in place, so there is nothing to copy back.
    rows = [
        HomeRow(key=f"cinema-{index}", title="", items=[entry.card for entry in group])
        for index, group in enumerate(groups)
        if group
    ]
    if rows:
        await _attach_match_scores(db, user, rows)


class TrackBody(BaseModel):
    type: str
    tmdb_id: int


@router.post("/cinema/track", response_model=CinemaTitle, dependencies=[Depends(csrf_protect)])
async def track(
    body: TrackBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CinemaTitle:
    if body.type != "movie":
        raise HTTPException(status_code=422, detail="only films play in cinemas")
    title = await ingest.ensure_title(db, "movie", body.tmdb_id)
    listing = await _cinema_list(db, user, create=True)
    assert listing is not None
    existing = (
        await db.execute(
            select(ListItem).where(ListItem.list_id == listing.id, ListItem.title_id == title.id)
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(ListItem(list_id=listing.id, title_id=title.id, added_by=user.id))
    opens = theatrical_date(title.raw_tmdb or {}, user.country_code)
    await db.commit()
    return CinemaTitle(
        card=_card_from_title(title),
        opens_on=opens,
        in_cinemas_now=is_showing(opens),
        tracked=True,
    )


@router.delete("/cinema/track", status_code=204, dependencies=[Depends(csrf_protect)])
async def untrack(
    type: str,
    tmdb_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    listing = await _cinema_list(db, user)
    if listing is None:
        return
    title = (
        await db.execute(select(Title).where(Title.type == type, Title.tmdb_id == tmdb_id))
    ).scalar_one_or_none()
    if title is None:
        return
    item = (
        await db.execute(
            select(ListItem).where(ListItem.list_id == listing.id, ListItem.title_id == title.id)
        )
    ).scalar_one_or_none()
    if item is not None:
        await db.delete(item)
        await db.commit()


async def alert_on_openings(db: AsyncSession) -> dict[str, int]:
    """Worker job: tell people a week before something they are waiting for opens.

    One alert per film per person, a week ahead of the local release date,
    because the point is to leave time to make a plan rather than to announce
    a thing that already happened. A film tracked inside that week, or after
    it has already opened, gets its alert on the next run instead."""
    from app.models import Notification
    from app.notifications import service as notifications

    counters = {"checked": 0, "notified": 0}
    lists = (await db.execute(select(List).where(List.kind == CINEMA_LIST))).scalars().all()
    today = datetime.now(UTC).date()

    for listing in lists:
        person = (
            await db.execute(select(User).where(User.id == listing.user_id))
        ).scalar_one_or_none()
        if person is None:
            continue
        titles = (
            (
                await db.execute(
                    select(Title)
                    .join(ListItem, ListItem.title_id == Title.id)
                    .where(ListItem.list_id == listing.id)
                )
            )
            .scalars()
            .all()
        )
        for title in titles:
            counters["checked"] += 1
            # tmdb.details is a live call, and this job runs hourly, so ask
            # only when the answer could plausibly have changed something.
            # A film we already know opens months from now cannot become due
            # before the next run, and re-fetching it every hour would cost
            # one request per tracked film per hour for no new information.
            opens = theatrical_date(title.raw_tmdb or {}, person.country_code)
            if opens is None or alert_due(opens, today, LEAD_DAYS + 7):
                try:
                    payload = await tmdb.details(db, "movie", title.tmdb_id)
                    opens = theatrical_date(payload, person.country_code)
                except (tmdb.TmdbNotConfigured, tmdb.TmdbError):
                    pass
            if opens is None or not alert_due(opens, today):
                continue

            already = (
                await db.execute(
                    select(Notification).where(
                        Notification.user_id == person.id,
                        Notification.title_id == title.id,
                        Notification.kind == "cinema",
                    )
                )
            ).scalar_one_or_none()
            if already is not None:
                continue

            # Say the true thing. A film a week out is not showing yet, and
            # telling someone to book something that has not opened is the
            # kind of small lie that costs trust in every later alert.
            days = (opens - today).days
            if days > 1:
                text = f"{title.name} opens in cinemas in {days} days."
                push_title = "Opening soon"
            elif days == 1:
                text = f"{title.name} opens in cinemas tomorrow."
                push_title = "Opening tomorrow"
            elif days == 0:
                text = f"{title.name} opens in cinemas today. Time to book."
                push_title = "Opening today"
            else:
                text = f"{title.name} is in cinemas now. Time to book."
                push_title = "In cinemas"

            made = await notifications.notify(
                db,
                person,
                "cinema",
                text,
                title=title,
                payload={"tmdb_id": title.tmdb_id, "type": "movie", "opens_on": opens.isoformat()},
                push_title=push_title,
            )
            counters["notified"] += 1 if made else 0
        await db.commit()
    return counters
