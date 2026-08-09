from collections import Counter
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth.deps import get_current_user
from app.db import get_db
from app.models import User, WatchEvent

router = APIRouter(prefix="/api")


class StatsTotals(BaseModel):
    watched: int
    hours: float
    loved: int
    rated: int
    avg_rating: float | None
    this_year: int


class NameCount(BaseModel):
    name: str
    count: int
    extra: str | None = None


class TitleHighlight(BaseModel):
    tmdb_id: int
    type: str
    name: str
    poster_path: str | None
    year: int | None
    rating_10: int | None
    loved: bool


class DayCount(BaseModel):
    day: str  # ISO date
    count: int
    # What was watched that day, so the tooltip can name it rather than
    # just counting. Capped, because one binge should not send fifty names.
    names: list[str] = []
    # The same titles with their artwork, so clicking a square can show the
    # posters rather than a list of words.
    titles: list[TitleHighlight] = []


class MonthCount(BaseModel):
    month: str
    count: int


class PersonCount(BaseModel):
    name: str
    count: int
    profile_path: str | None = None
    person_id: int | None = None


class StatsResponse(BaseModel):
    totals: StatsTotals
    genres: list[NameCount]
    monthly: list[MonthCount]
    ratings: list[MonthCount]
    top_actors: list[NameCount]
    streak_longest: int
    wrap: dict
    # The richer view: who and what, not just how many.
    people: list[PersonCount]
    directors: list[PersonCount]
    languages: list[NameCount]
    decades: list[NameCount]
    highest_rated: list[TitleHighlight]
    recent: list[TitleHighlight]
    by_year: list[NameCount]
    runtime_buckets: list[NameCount]
    # One entry per day you watched something, for the year grid. Days with
    # nothing are omitted rather than sent as zeroes: a full year of empty
    # cells is 365 rows of nothing on every request.
    days: list[DayCount]
    # Every year with something in it, newest first, for the switcher.
    years: list[int]
    # A ranked ten with artwork, which reads very differently from a bar.
    top_ten: list[TitleHighlight]
    longest: list[TitleHighlight]
    # Franchises watched more than once, so a run through a series shows.
    collections: list[NameCount]


def _month_key(when: datetime) -> str:
    return f"{when.year:04d}-{when.month:02d}"


def _highlight(event: WatchEvent) -> TitleHighlight:
    return TitleHighlight(
        tmdb_id=event.title.tmdb_id,
        type=event.title.type,
        name=event.title.name,
        poster_path=event.title.poster_path,
        year=event.title.year,
        rating_10=event.rating_10,
        loved=event.loved,
    )


@router.get("/stats", response_model=StatsResponse)
async def stats(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> StatsResponse:
    events = (
        (
            await db.execute(
                select(WatchEvent)
                .options(joinedload(WatchEvent.title))
                .where(WatchEvent.user_id == user.id)
                .order_by(WatchEvent.watched_at)
            )
        )
        .scalars()
        .all()
    )

    now = datetime.now(UTC)
    minutes = 0
    genres: Counter[str] = Counter()
    monthly: Counter[str] = Counter()
    ratings: Counter[int] = Counter()
    actors: Counter[str] = Counter()
    actor_photos: dict[str, str | None] = {}
    actor_ids: dict[str, int | None] = {}
    directors: Counter[str] = Counter()
    director_photos: dict[str, str | None] = {}
    director_ids: dict[str, int | None] = {}
    languages: Counter[str] = Counter()
    decades: Counter[str] = Counter()
    runtimes: Counter[str] = Counter()
    days_watched: set = set()
    year_counter: Counter[int] = Counter()
    day_counter: Counter[str] = Counter()
    day_names: dict[str, list[str]] = {}
    day_titles: dict[str, list[TitleHighlight]] = {}
    title_best: dict[str, tuple[float, str]] = {}
    collections: Counter[str] = Counter()

    for event in events:
        title = event.title
        minutes += title.runtime or 0
        watched = event.watched_at
        if watched.tzinfo is None:
            watched = watched.replace(tzinfo=UTC)
        days_watched.add(watched.date())
        year_counter[watched.year] += 1
        key = watched.date().isoformat()
        day_counter[key] += 1
        names = day_names.setdefault(key, [])
        if len(names) < 6:
            names.append(title.name)
        arts = day_titles.setdefault(key, [])
        if len(arts) < 12:
            arts.append(_highlight(event))
        if now - watched <= timedelta(days=365):
            monthly[_month_key(watched)] += 1
        if event.rating_10 is not None:
            ratings[event.rating_10] += 1
        for genre in title.genres or []:
            name = genre.get("name")
            if name:
                genres[name] += 1
        cast = ((title.raw_tmdb or {}).get("credits") or {}).get("cast") or []
        for member in cast[:8]:
            if member.get("name"):
                actors[member["name"]] += 1
                actor_photos.setdefault(member["name"], member.get("profile_path"))
                actor_ids.setdefault(member["name"], member.get("id"))
        crew = ((title.raw_tmdb or {}).get("credits") or {}).get("crew") or []
        for member in crew:
            if member.get("job") == "Director" and member.get("name"):
                directors[member["name"]] += 1
                director_photos.setdefault(member["name"], member.get("profile_path"))
                director_ids.setdefault(member["name"], member.get("id"))
        if title.collection_name:
            collections[title.collection_name] += 1
        if title.original_language:
            languages[title.original_language] += 1
        if title.year:
            decades[f"{(title.year // 10) * 10}s"] += 1
        if title.runtime:
            if title.runtime < 90:
                runtimes["Under 90 min"] += 1
            elif title.runtime <= 120:
                runtimes["90 to 120 min"] += 1
            elif title.runtime <= 150:
                runtimes["2 to 2.5 hours"] += 1
            else:
                runtimes["Over 2.5 hours"] += 1
        score = (event.rating_10 or 0) + (5 if event.loved else 0)
        key = title.name
        if key not in title_best or score > title_best[key][0]:
            title_best[key] = (score, key)

    # Longest run of consecutive days with at least one watch.
    longest = 0
    run = 0
    previous = None
    for day in sorted(days_watched):
        run = run + 1 if previous is not None and (day - previous).days == 1 else 1
        longest = max(longest, run)
        previous = day

    rated = [e for e in events if e.rating_10 is not None]
    # Calendar months, walked back one at a time: 30-day steps drift and
    # would duplicate a month while skipping February.
    months = []
    year, month = now.year, now.month
    for _ in range(12):
        months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    months.reverse()

    this_year_events = [
        e
        for e in events
        if (e.watched_at.replace(tzinfo=UTC) if e.watched_at.tzinfo is None else e.watched_at).year
        == now.year
    ]
    favorite = None
    if this_year_events:
        best = max(
            this_year_events,
            key=lambda e: (e.rating_10 or 0) + (5 if e.loved else 0),
        )
        favorite = best.title.name

    return StatsResponse(
        totals=StatsTotals(
            watched=len(events),
            hours=round(minutes / 60, 1),
            loved=sum(1 for e in events if e.loved),
            rated=len(rated),
            avg_rating=(
                round(sum(e.rating_10 or 0 for e in rated) / len(rated), 1) if rated else None
            ),
            this_year=len(this_year_events),
        ),
        genres=[NameCount(name=n, count=c) for n, c in genres.most_common(10)],
        monthly=[MonthCount(month=m, count=monthly.get(m, 0)) for m in months],
        ratings=[MonthCount(month=str(r), count=ratings.get(r, 0)) for r in range(1, 11)],
        top_actors=[
            NameCount(name=n, count=c, extra=actor_photos.get(n)) for n, c in actors.most_common(8)
        ],
        streak_longest=longest,
        people=[
            PersonCount(
                name=n,
                count=c,
                profile_path=actor_photos.get(n),
                person_id=actor_ids.get(n),
            )
            for n, c in actors.most_common(12)
        ],
        directors=[
            PersonCount(
                name=n,
                count=c,
                profile_path=director_photos.get(n),
                person_id=director_ids.get(n),
            )
            for n, c in directors.most_common(8)
        ],
        languages=[NameCount(name=n, count=c) for n, c in languages.most_common(10)],
        decades=[NameCount(name=n, count=c) for n, c in sorted(decades.items())],
        runtime_buckets=[
            NameCount(name=n, count=runtimes.get(n, 0))
            for n in ("Under 90 min", "90 to 120 min", "2 to 2.5 hours", "Over 2.5 hours")
            if runtimes.get(n)
        ],
        by_year=[NameCount(name=str(y), count=c) for y, c in sorted(year_counter.items())],
        days=[
            DayCount(
                day=day,
                count=count,
                names=day_names.get(day, []),
                titles=day_titles.get(day, []),
            )
            for day, count in sorted(day_counter.items())
        ],
        years=sorted(year_counter, reverse=True),
        highest_rated=[
            _highlight(e)
            for e in sorted(
                (e for e in events if e.rating_10 is not None or e.loved),
                key=lambda e: (e.rating_10 or 0) + (2 if e.loved else 0),
                reverse=True,
            )[:12]
        ],
        recent=[_highlight(e) for e in list(reversed(events))[:12]],
        top_ten=[
            _highlight(e)
            for e in sorted(
                (e for e in events if e.rating_10 is not None or e.loved),
                key=lambda e: ((e.rating_10 or 0) + (2 if e.loved else 0), e.watched_at),
                reverse=True,
            )[:10]
        ],
        longest=[
            _highlight(e)
            for e in sorted(
                (e for e in events if e.title.runtime),
                key=lambda e: e.title.runtime or 0,
                reverse=True,
            )[:8]
        ],
        # Two or more from the same franchise means it was a run, not a
        # one-off, which is the only reason it is interesting.
        collections=[NameCount(name=n, count=c) for n, c in collections.most_common(8) if c > 1],
        wrap={
            "year": now.year,
            "watched": len(this_year_events),
            "hours": round(sum(e.title.runtime or 0 for e in this_year_events) / 60, 1),
            "favorite": favorite,
            "top_genre": genres.most_common(1)[0][0] if genres else None,
        },
    )
