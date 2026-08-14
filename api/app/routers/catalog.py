import asyncio
import contextlib
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from datetime import date as dt_date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.catalog import bootstrap, genre_map, ingest, local, omdb, omdb_source, tmdb
from app.catalog.providers import click_out_url
from app.config import get_settings
from app.countries import for_user as countries_for
from app.db import get_db
from app.models import Availability, FollowedPerson, Title, User

logger = logging.getLogger("roundtable.catalog")

router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])


class TitleCard(BaseModel):
    tmdb_id: int
    type: str
    name: str
    poster_path: str | None
    backdrop_path: str | None
    year: int | None
    # The full date, not only the year. A franchise that ships four films in
    # one year cannot be put in release order without it.
    release_date: dt_date | None = None
    tmdb_rating: float | None
    # 0-100 fit for the signed-in person, absent until there is enough signal.
    match: int | None = None
    # Age rating, present only when the viewer turned the parents guide on.
    certification: str | None = None


class HomeRow(BaseModel):
    key: str
    title: str
    items: list[TitleCard]


class HomeResponse(BaseModel):
    rows: list[HomeRow]


def _card_from_tmdb(item: dict, media_type: str | None = None) -> TitleCard | None:
    kind = media_type or item.get("media_type")
    if kind not in ("movie", "tv"):
        return None
    raw = item.get("release_date") if kind == "movie" else item.get("first_air_date")
    year = int(raw[:4]) if raw and raw[:4].isdigit() else None
    released = None
    if raw:
        try:
            released = dt_date.fromisoformat(str(raw)[:10])
        except ValueError:
            released = None
    return TitleCard(
        tmdb_id=item["id"],
        type=kind,
        name=item.get("title") or item.get("name") or "Untitled",
        poster_path=item.get("poster_path"),
        backdrop_path=item.get("backdrop_path"),
        year=year,
        release_date=released,
        tmdb_rating=item.get("vote_average"),
    )


def _cards(payload: dict, media_type: str | None = None) -> list[TitleCard]:
    cards = []
    for item in payload.get("results", []):
        card = _card_from_tmdb(item, media_type)
        if card and card.poster_path:
            cards.append(card)
    return cards


def _tmdb_unavailable(exc: Exception) -> HTTPException:
    if isinstance(exc, tmdb.TmdbNotConfigured):
        return HTTPException(status_code=503, detail="tmdb_not_configured")
    return HTTPException(status_code=502, detail="tmdb_unavailable")


async def _personal_rows_iter(
    db: AsyncSession, user: User, media_type: str | None = None
) -> AsyncIterator[HomeRow]:
    """Personalized rows, one at a time, so the first can be on screen
    while the rest are still being cut from the pool."""
    from app.ai import rails

    async for shelf in rails.build_iter(db, user, media_type):
        yield HomeRow(
            key=shelf.key,
            title=shelf.title,
            items=[_card_from_title(t) for t in shelf.titles],
        )


async def _movie_night_row(
    db: AsyncSession, user: User, rows: list[HomeRow], media_type: str | None = None
) -> HomeRow | None:
    """The blended shelf, present only when AI is enabled and tastes exist.
    Failures never break the home page."""
    from app.ai import client as ai_client
    from app.ai import rails
    from app.ai import taste as taste_module

    try:
        my_taste = await taste_module.get_taste(db, user)
        if my_taste is None:
            return None
        exclude = await taste_module.watched_title_ids(db, user)
        exclude |= await rails.unwatchable_title_ids(db)
        # Whatever the shelves above already used. Without this the blended
        # row is mostly a copy of "Picked for you" whenever the other person
        # has told us little, which is exactly when it is least useful.
        shown = {(item.type, item.tmdb_id) for shelf in rows for item in shelf.items}

        others = (
            (
                await db.execute(
                    select(User).where(
                        User.id != user.id,
                        User.tenant_id == user.tenant_id,
                        User.is_active.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        other_tastes = []
        for other in others:
            other_taste = await taste_module.get_taste(db, other)
            if other_taste is not None:
                other_tastes.append((other, other_taste))
        if other_tastes:
            import numpy as np  # noqa: F401

            blended = taste_module.blend_tastes([my_taste] + [t for _, t in other_tastes])
            exclude_both = set(exclude)
            for other, _ in other_tastes:
                exclude_both |= await taste_module.watched_title_ids(db, other)
            night = await taste_module.diversified_ranking(
                db, blended, 40, exclude_both, media_type=media_type
            )
            cards = [_card_from_title(t) for t, _ in night if t.poster_path]
            fresh = [c for c in cards if (c.type, c.tmdb_id) not in shown]
            # A preference, not a rule. On a catalog large enough to have a
            # choice this row stops being a copy of "Picked for you"; on one
            # too small to have a choice, showing it anyway beats hiding the
            # feature until the catalog grows.
            items = (fresh if len(fresh) >= 4 else cards)[:20]
            if items:
                return HomeRow(
                    key="movie-night",
                    title="Movie night for both of you",
                    items=items,
                )
    except (ai_client.AIDisabled, ai_client.AIError):
        return None
    return None


async def _ai_home_rows(
    db: AsyncSession, user: User, media_type: str | None = None
) -> list[HomeRow]:
    """All personalized rows at once, for pages that want the finished list."""
    rows = [row async for row in _personal_rows_iter(db, user, media_type)]
    night = await _movie_night_row(db, user, rows, media_type)
    if night is not None:
        rows.append(night)
    return rows


# Where to look when the person's own country has no rating on file.
CERT_FALLBACK = ("US", "GB", "DE", "FR")


def _certification_for(title, user) -> str | None:
    """The age rating that means something to this viewer: their country
    first, then a widely understood one. Never invented."""
    certs = title.certifications or {}
    if user is not None and user.country_code and certs.get(user.country_code):
        return certs[user.country_code]
    for country in CERT_FALLBACK:
        if certs.get(country):
            return certs[country]
    return None


def _card_from_title(title) -> TitleCard:
    return TitleCard(
        tmdb_id=title.tmdb_id,
        type=title.type,
        name=title.name,
        poster_path=title.poster_path,
        backdrop_path=title.backdrop_path,
        year=title.year,
        tmdb_rating=title.tmdb_rating,
    )


async def _hide_watched(db: AsyncSession, user: User, rows: list[HomeRow]) -> list[HomeRow]:
    """Drop titles already watched from every shelf.

    The personalized rows already exclude them; the trending and genre
    shelves come straight from the catalog and do not, which is what makes
    the setting worth having. A shelf left with almost nothing is dropped
    rather than shown half empty."""
    from app.models import WatchEvent

    seen = {
        (kind, tmdb_id)
        for kind, tmdb_id in (
            await db.execute(
                select(Title.type, Title.tmdb_id)
                .join(WatchEvent, WatchEvent.title_id == Title.id)
                .where(WatchEvent.user_id == user.id)
            )
        ).all()
    }
    if not seen:
        return rows
    kept = []
    for row in rows:
        items = [i for i in row.items if (i.type, i.tmdb_id) not in seen]
        if len(items) >= 4:
            kept.append(row.model_copy(update={"items": items}))
    return kept


@router.get("/for-you", response_model=HomeResponse)
async def for_you(
    media: str = Query("all", pattern="^(all|movie|tv)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HomeResponse:
    """The personalized shelves on their own, for one kind of thing.

    Films and Series are separate pages, and a page called Films that opens
    on a grid of whatever is popular is not a page about you. This is what
    goes above that grid. It carries no trending or genre fallback: when
    there is nothing personal to say yet it returns nothing, and the grid is
    the whole page, which is the honest outcome."""
    media_type = None if media == "all" else media
    rows = await _ai_home_rows(db, user, media_type)
    if (user.prefs or {}).get("hide_watched"):
        rows = await _hide_watched(db, user, rows)
    await _attach_match_scores(db, user, rows)
    await db.commit()
    return HomeResponse(rows=rows)


HOME_FRESH_SECONDS = 180
_HOME_KEY = "wd:home:v1:{user_id}"


async def invalidate_home(user_id: str) -> None:
    """Drop one person's cached home. Called wherever taste changes, so
    the next look at the page reflects what they just did."""
    from redis.asyncio import Redis

    try:
        redis = Redis.from_url(get_settings().redis_url)
        try:
            await redis.delete(_HOME_KEY.format(user_id=user_id))
        finally:
            await redis.aclose()
    except Exception:
        logger.exception("home cache invalidation failed for %s", user_id)


async def _iter_home_rows(
    db: AsyncSession, user: User, unavailable: list[Exception]
) -> AsyncIterator[HomeRow]:
    """Every home row in reading order, each yielded the moment it exists.

    Personalized shelves first, then the blended night row, then the
    catalog-wide shelves. When TMDB is missing the local catalog rows take
    over; when even those are empty the caller decides what the absence
    means, via `unavailable`."""
    personal: list[HomeRow] = []
    async for row in _personal_rows_iter(db, user):
        personal.append(row)
        yield row
    night = await _movie_night_row(db, user, personal)
    if night is not None:
        yield night
    try:
        movies = await tmdb.trending(db, "movie")
        yield HomeRow(key="trending-movies", title="Trending films", items=_cards(movies, "movie"))
        tv = await tmdb.trending(db, "tv")
        yield HomeRow(key="trending-tv", title="Trending series", items=_cards(tv, "tv"))

        # Cinema from the languages this person cares about, before the
        # generic genre shelf.
        preferred = list((user.prefs or {}).get("languages", []))
        for code, label in bootstrap.LANGUAGE_ROWS:
            if preferred and code not in preferred:
                continue
            payload = await tmdb.discover(
                db,
                "movie",
                {
                    "with_original_language": code,
                    "sort_by": "popularity.desc",
                    "vote_count.gte": 50,
                },
            )
            items = _cards(payload, "movie")
            if items:
                yield HomeRow(key=f"lang-{code}", title=label, items=items)

        for media_type, genre_id, label in bootstrap.CATEGORY_ROWS:
            payload = await tmdb.discover(
                db,
                media_type,
                {"with_genres": genre_id, "sort_by": "popularity.desc", "vote_count.gte": 100},
            )
            items = _cards(payload, media_type)
            if items:
                yield HomeRow(key=f"{media_type}-genre-{genre_id}", title=label, items=items)
    except (tmdb.TmdbNotConfigured, tmdb.TmdbError) as exc:
        # No TMDB: the local catalog, primed from OMDb, carries the page.
        unavailable.append(exc)
        for row in await _local_home_rows(db, user):
            yield row


async def _finished_home_rows(
    db: AsyncSession, user: User, unavailable: list[Exception]
) -> AsyncIterator[HomeRow]:
    """The row iterator with this person's presentation applied: watched
    titles hidden when they asked, match scores and age ratings stamped."""
    hide = bool((user.prefs or {}).get("hide_watched"))
    async for row in _iter_home_rows(db, user, unavailable):
        if hide:
            filtered = await _hide_watched(db, user, [row])
            if not filtered:
                continue
            row = filtered[0]
        await _attach_match_scores(db, user, [row])
        yield row


async def _build_home(db: AsyncSession, user: User) -> HomeResponse:
    unavailable: list[Exception] = []
    rows = [row async for row in _finished_home_rows(db, user, unavailable)]
    if not rows and unavailable:
        raise _tmdb_unavailable(unavailable[0])
    await db.commit()
    return HomeResponse(rows=rows)


async def _load_home_cache(user_id: str) -> dict | None:
    from redis.asyncio import Redis

    try:
        redis = Redis.from_url(get_settings().redis_url)
        try:
            raw = await redis.get(_HOME_KEY.format(user_id=user_id))
        finally:
            await redis.aclose()
        return json.loads(raw) if raw else None
    except Exception:
        # No redis is no excuse for no home page.
        return None


async def _store_home(user_id: str, response: HomeResponse) -> None:
    from redis.asyncio import Redis

    redis = Redis.from_url(get_settings().redis_url)
    try:
        await redis.set(
            _HOME_KEY.format(user_id=user_id),
            json.dumps({"at": time.time(), "rows": response.model_dump(mode="json")["rows"]}),
            ex=60 * 60 * 24,
        )
    finally:
        await redis.aclose()


async def _refresh_home(user_id: str) -> None:
    """Rebuild one person's home in the background, at most one at a time.

    The page itself is 10+ seconds of taste math on a small server; nobody
    should ever sit through it twice. Any failure here just leaves the
    cached page in place."""
    from redis.asyncio import Redis

    from app.db import get_sessionmaker

    try:
        redis = Redis.from_url(get_settings().redis_url)
        try:
            # The lock expires on its own, covering a crashed rebuild.
            locked = await redis.set(f"wd:home:refresh:{user_id}", "1", nx=True, ex=300)
            if not locked:
                return
        finally:
            await redis.aclose()
        async with get_sessionmaker()() as db:
            fresh = (
                await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
            ).scalar_one_or_none()
            if fresh is None or not fresh.is_active:
                return
            response = await _build_home(db, fresh)
        await _store_home(user_id, response)
    except Exception:
        logger.exception("background home rebuild failed for %s", user_id)


@router.get("/home", response_model=HomeResponse)
async def home(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> HomeResponse:
    """Serve the cached page instantly and rebuild it in the background.

    Only the very first request a person ever makes builds inline. After
    that the cache answers, and anything older than HOME_FRESH_SECONDS
    triggers a refresh that the NEXT request benefits from."""
    cached = await _load_home_cache(str(user.id))
    if cached is not None:
        if time.time() - cached.get("at", 0) > HOME_FRESH_SECONDS:
            asyncio.get_running_loop().create_task(_refresh_home(str(user.id)))
        return HomeResponse.model_validate({"rows": cached.get("rows", [])})

    response = await _build_home(db, user)
    try:
        await _store_home(str(user.id), response)
    except Exception:
        logger.exception("storing home cache failed for %s", user.id)
    return response


@router.get("/home/stream")
async def home_stream(user: User = Depends(get_current_user)) -> StreamingResponse:
    """The home page as newline-delimited JSON, one row per line.

    Warm cache streams everything in one burst, exactly like /home. A cold
    build streams each shelf the moment it exists, so the first row is on
    screen seconds before the last one is computed, and the finished page
    lands in the cache for next time."""

    async def rows() -> AsyncIterator[str]:
        cached = await _load_home_cache(str(user.id))
        if cached is not None:
            if time.time() - cached.get("at", 0) > HOME_FRESH_SECONDS:
                asyncio.get_running_loop().create_task(_refresh_home(str(user.id)))
            for row in cached.get("rows", []):
                yield json.dumps(row) + "\n"
            return
        # The request-scoped session is closed before a streaming body
        # runs (FastAPI tears down yield-dependencies first), so the
        # generator owns its session for the whole build.
        from app.db import get_sessionmaker

        unavailable: list[Exception] = []
        built: list[HomeRow] = []
        async with get_sessionmaker()() as db:
            async for row in _finished_home_rows(db, user, unavailable):
                built.append(row)
                yield row.model_dump_json() + "\n"
            await db.commit()
        if built:
            try:
                await _store_home(str(user.id), HomeResponse(rows=built))
            except Exception:
                logger.exception("storing home cache failed for %s", user.id)

    return StreamingResponse(
        rows(),
        media_type="application/x-ndjson",
        # nginx honours this and stops buffering, which is the whole point.
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
    )


async def _attach_match_scores(db: AsyncSession, user: User, rows: list[HomeRow]) -> None:
    """Stamp every card with how well it fits this person, and with the age
    rating when they asked to see one."""
    from app.ai import taste as taste_module

    pairs = {(card.type, card.tmdb_id) for row in rows for card in row.items}
    if not pairs:
        return
    lookup = {
        (t.type, t.tmdb_id): t.id
        for t in (
            await db.execute(
                select(Title).where(Title.tmdb_id.in_({tmdb_id for _, tmdb_id in pairs}))
            )
        ).scalars()
    }
    scores = await taste_module.match_scores(db, user, list(lookup.values()))
    wants_ratings = bool((user.prefs or {}).get("parents_guide"))
    certs = (
        {
            t.id: _certification_for(t, user)
            for t in (
                await db.execute(select(Title).where(Title.id.in_(lookup.values())))
            ).scalars()
        }
        if wants_ratings
        else {}
    )
    if not scores and not certs:
        return
    for row in rows:
        for card in row.items:
            title_id = lookup.get((card.type, card.tmdb_id))
            if title_id is None:
                continue
            card.match = scores.get(title_id)
            if wants_ratings:
                card.certification = certs.get(title_id)


async def _local_home_rows(db: AsyncSession, user: User | None = None) -> list[HomeRow]:
    """Rows built from the local catalog. This is the live path whenever TMDB
    is unavailable, so it carries the full category shelf."""
    rows: list[HomeRow] = []

    top = await local.top_rated(db, limit=20)
    if top:
        rows.append(
            HomeRow(
                key="top-rated",
                title="Best rated",
                items=[_card_from_title(t) for t in top],
            )
        )
    popular = await local.recent(db, "movie", limit=20)
    if popular:
        rows.append(
            HomeRow(
                key="popular-films",
                title="Popular films",
                items=[_card_from_title(t) for t in popular],
            )
        )
    series = await local.recent(db, "tv", limit=20)
    if series:
        rows.append(
            HomeRow(
                key="popular-series",
                title="Popular series",
                items=[_card_from_title(t) for t in series],
            )
        )

    # Languages the person told us they care about come before the rest.
    preferred = list((user.prefs or {}).get("languages", [])) if user else []
    language_rows = sorted(
        bootstrap.LANGUAGE_ROWS,
        key=lambda pair: 0 if pair[0] in preferred else 1,
    )
    for code, label in language_rows:
        titles = await local.by_language(db, code, limit=20)
        if len(titles) >= 3:
            rows.append(
                HomeRow(
                    key=f"lang-{code}",
                    title=label,
                    items=[_card_from_title(t) for t in titles],
                )
            )

    for media_type, genre_id, label in bootstrap.CATEGORY_ROWS:
        titles = await local.by_genre(db, media_type, genre_id, limit=20)
        if len(titles) >= 3:
            rows.append(
                HomeRow(
                    key=f"{media_type}-{genre_id}",
                    title=label,
                    items=[_card_from_title(t) for t in titles],
                )
            )
    return rows


class PersonCard(BaseModel):
    person_id: int
    name: str
    profile_path: str | None
    # What they are best known for, so a name has something behind it.
    known_for: str
    you_follow: bool = False


class SearchResponse(BaseModel):
    results: list[TitleCard]
    page: int
    total_pages: int
    # People matching the same words. One search box, both kinds of answer.
    people: list[PersonCard] = []


def _people_from(payload: dict) -> list[PersonCard]:
    """Actors and directors out of a multi-search, best known work first."""
    out = []
    for item in payload.get("results", []):
        if item.get("media_type") != "person" or not item.get("id"):
            continue
        known = [
            k.get("title") or k.get("name")
            for k in (item.get("known_for") or [])
            if k.get("title") or k.get("name")
        ]
        out.append(
            PersonCard(
                person_id=int(item["id"]),
                name=str(item.get("name") or "Unknown"),
                profile_path=item.get("profile_path"),
                known_for=", ".join(known[:3]),
            )
        )
    # Popularity order from upstream is already sensible; cap it so people
    # never crowd out the titles.
    return out[:8]


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(min_length=1, max_length=200),
    page: int = Query(1, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    try:
        payload = await tmdb.search_multi(db, q, page)
    except (tmdb.TmdbNotConfigured, tmdb.TmdbError) as exc:
        # Local index first: instant, and it already covers everything seen.
        found = await local.search(db, q)
        known = {t.imdb_id for t in found if t.imdb_id}

        # Then widen with a live OMDb lookup so search reaches the whole
        # catalogue, not only what has been fetched before.
        if omdb_source.configured():
            with contextlib.suppress(omdb_source.OmdbError, omdb_source.OmdbNotConfigured):
                for hit in (await omdb_source.search(db, q, page))[:10]:
                    imdb_id = hit.get("imdbID")
                    if not imdb_id or imdb_id in known:
                        continue
                    data = await omdb_source.detail_by_id(db, imdb_id)
                    if data is None:
                        continue
                    title = await omdb_source.upsert_from_omdb(db, data)
                    if title is not None:
                        known.add(imdb_id)
                        found.append(title)

        if not found and not await local.has_any(db):
            raise _tmdb_unavailable(exc) from exc
        await db.commit()
        return SearchResponse(
            results=[_card_from_title(t) for t in found], page=page, total_pages=1
        )
    people = _people_from(payload)
    if people:
        followed = set(
            (
                await db.execute(
                    select(FollowedPerson.person_id).where(FollowedPerson.user_id == user.id)
                )
            )
            .scalars()
            .all()
        )
        for person in people:
            person.you_follow = person.person_id in followed
    await db.commit()
    return SearchResponse(
        results=_cards(payload),
        page=payload.get("page", 1),
        total_pages=payload.get("total_pages", 1),
        people=people,
    )


class CombinedGenre(BaseModel):
    name: str
    movie_ids: list[int]
    tv_ids: list[int]


class GenresResponse(BaseModel):
    movie: list[dict]
    tv: list[dict]
    # One label per genre, resolved to whichever ids each side uses, so a
    # filter survives switching between films and series.
    combined: list[CombinedGenre] = []


@router.get("/genres", response_model=GenresResponse)
async def genre_lists(db: AsyncSession = Depends(get_db)) -> GenresResponse:
    try:
        movie = await tmdb.genres(db, "movie")
        tv = await tmdb.genres(db, "tv")
    except (tmdb.TmdbNotConfigured, tmdb.TmdbError) as exc:
        # Genres present in the real local catalog, so browse chips never
        # offer a category with nothing behind it.
        local_movie = await local.genres(db, "movie")
        local_tv = await local.genres(db, "tv")
        if not local_movie and not local_tv:
            raise _tmdb_unavailable(exc) from exc
        await db.commit()
        return GenresResponse(
            movie=local_movie,
            tv=local_tv,
            combined=[CombinedGenre(**c) for c in genre_map.build(local_movie, local_tv)],
        )
    await db.commit()
    movie_list = movie.get("genres", [])
    tv_list = tv.get("genres", [])
    return GenresResponse(
        movie=movie_list,
        tv=tv_list,
        combined=[CombinedGenre(**c) for c in genre_map.build(movie_list, tv_list)],
    )


# What each sort means upstream. "new" needs its own date field per side.
SORT_PARAMS: dict[str, dict] = {
    "popular": {"sort_by": "popularity.desc", "vote_count.gte": 50},
    "top": {"sort_by": "vote_average.desc", "vote_count.gte": 300},
    "new": {"sort_by": "primary_release_date.desc", "vote_count.gte": 20},
}


async def _genre_ids(db: AsyncSession, genre: str, media_type: str) -> list[int]:
    """A genre filter is a label, not an id, so it means the same thing on
    both sides. Bare digits still work for older clients and direct calls."""
    if genre.isdigit():
        return [int(genre)]
    try:
        movie_list = (await tmdb.genres(db, "movie")).get("genres", [])
        tv_list = (await tmdb.genres(db, "tv")).get("genres", [])
    except (tmdb.TmdbNotConfigured, tmdb.TmdbError):
        movie_list = await local.genres(db, "movie")
        tv_list = await local.genres(db, "tv")
    return genre_map.resolve(genre, media_type, genre_map.build(movie_list, tv_list))


async def _discover_side(
    db: AsyncSession,
    media_type: str,
    genre: str | None,
    sort: str,
    page: int,
    language: str | None = None,
) -> dict:
    params: dict = {"page": page, **SORT_PARAMS[sort]}
    if sort == "new" and media_type == "tv":
        params["sort_by"] = "first_air_date.desc"
    if language:
        params["with_original_language"] = language
    if genre:
        ids = await _genre_ids(db, genre, media_type)
        if not ids:
            # This side has no equivalent genre. Say so with an empty page
            # rather than quietly returning everything.
            return {"page": page, "total_pages": 0, "results": []}
        params["with_genres"] = ",".join(str(i) for i in ids)
    return await tmdb.discover(db, media_type, params)


def _interleave(movies: list[TitleCard], shows: list[TitleCard]) -> list[TitleCard]:
    """Alternate the two sides so neither dominates the top of the grid."""
    out: list[TitleCard] = []
    for i in range(max(len(movies), len(shows))):
        if i < len(movies):
            out.append(movies[i])
        if i < len(shows):
            out.append(shows[i])
    return out


@router.get("/browse", response_model=SearchResponse)
async def browse(
    type: str = Query("movie", pattern="^(movie|tv|all)$"),
    genre: str | None = None,
    # Where it is from, which is how people think about a whole category the
    # genre list has no word for: K-drama, anime, Turkish drama.
    language: str | None = Query(None, pattern="^[a-z]{2}$"),
    sort: str = Query("popular", pattern="^(popular|top|new)$"),
    page: int = Query(1, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    try:
        if type == "all":
            movie_payload = await _discover_side(db, "movie", genre, sort, page, language)
            tv_payload = await _discover_side(db, "tv", genre, sort, page, language)
            await db.commit()
            return SearchResponse(
                results=_interleave(_cards(movie_payload, "movie"), _cards(tv_payload, "tv")),
                page=page,
                total_pages=max(
                    movie_payload.get("total_pages", 1), tv_payload.get("total_pages", 1)
                ),
            )
        payload = await _discover_side(db, type, genre, sort, page, language)
    except (tmdb.TmdbNotConfigured, tmdb.TmdbError) as exc:
        ids: list[int] = []
        if genre:
            ids = await _genre_ids(db, genre, "movie" if type in ("movie", "all") else "tv")
            if type == "all":
                ids += await _genre_ids(db, genre, "tv")
        found = await local.browse(
            db, None if type == "all" else type, ids, sort, limit=60, language=language
        )
        if not found and not await local.has_any(db):
            raise _tmdb_unavailable(exc) from exc
        await db.commit()
        return SearchResponse(results=[_card_from_title(t) for t in found], page=1, total_pages=1)
    await db.commit()
    return SearchResponse(
        results=_cards(payload, type),
        page=payload.get("page", 1),
        total_pages=payload.get("total_pages", 1),
    )


class CastMember(BaseModel):
    name: str
    character: str | None
    profile_path: str | None
    # TMDB person id, so every face links to their own page.
    person_id: int | None = None


class ProviderEntry(BaseModel):
    provider_name: str
    logo_path: str | None
    kind: str
    url: str | None


class TitleDetail(BaseModel):
    id: str
    tmdb_id: int
    type: str
    name: str
    original_name: str | None
    year: int | None
    overview: str | None
    original_language: str | None
    runtime: int | None
    genres: list[dict]
    keywords: list[str]
    poster_path: str | None
    backdrop_path: str | None
    tmdb_rating: float | None
    tmdb_votes: int | None
    imdb_rating: float | None
    rt_score: int | None
    metacritic: int | None
    trailer_youtube_key: str | None
    cast: list[CastMember]
    availability: dict[str, list[ProviderEntry]]
    countries: list[str]
    # Credits and context that come with the catalog record.
    director: str | None = None
    country: str | None = None
    rated: str | None = None
    awards: str | None = None
    imdb_id: str | None = None
    # 0-100 fit for the signed-in person.
    match: int | None = None
    # Official age ratings by country, and the one for this person's country.
    certifications: dict[str, str] = {}
    certification: str | None = None
    collection_id: int | None = None
    collection_name: str | None = None


def _trailer_key(raw: dict | None) -> str | None:
    videos = ((raw or {}).get("videos") or {}).get("results") or []
    trailers = [v for v in videos if v.get("site") == "YouTube" and v.get("type") == "Trailer"]
    official = [v for v in trailers if v.get("official")]
    pick = (official or trailers)[:1]
    return pick[0]["key"] if pick else None


def _cast(raw: dict | None, limit: int = 12) -> list[CastMember]:
    members = ((raw or {}).get("credits") or {}).get("cast") or []
    return [
        CastMember(
            name=m.get("name", ""),
            character=m.get("character"),
            profile_path=m.get("profile_path"),
            person_id=m.get("id"),
        )
        for m in members[:limit]
    ]


def _where_they_watch(user: User) -> list[str]:
    """The countries this person actually asked about.

    This used to be their country plus every other account's on the
    instance, which was wrong in both directions at once. Somebody in Egypt
    who had added Britain and the United States saw neither, because their
    own choices were never consulted, and did see Morocco, because another
    user lives there. Every Marvel film sat in the table marked Disney Plus
    under GB and US and the page never asked for those rows.

    app.countries.for_user is the one answer to this question, and the
    settings page promises exactly it: "availability, cinema listings and
    release alerts all widen to cover these". Six other callers already used
    it; this was the one that did not.
    """
    return countries_for(user) or [get_settings().default_country]


@router.get("/titles/{media_type}/{tmdb_id}", response_model=TitleDetail)
async def title_detail(
    media_type: str,
    tmdb_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TitleDetail:
    if media_type not in ("movie", "tv"):
        raise HTTPException(status_code=404, detail="unknown media type")
    try:
        title = await ingest.ensure_title(db, media_type, tmdb_id)
    except tmdb.TmdbNotConfigured as exc:
        raise _tmdb_unavailable(exc) from exc
    except tmdb.TmdbError as exc:
        raise _tmdb_unavailable(exc) from exc

    await omdb.refresh_title_scores(db, title)

    countries = _where_they_watch(user)
    # Explicit query: the async session cannot lazy-load the relationship.
    entries = (
        (
            await db.execute(
                select(Availability).where(
                    Availability.title_id == title.id, Availability.country.in_(countries)
                )
            )
        )
        .scalars()
        .all()
    )
    availability: dict[str, list[ProviderEntry]] = {}
    for entry in entries:
        availability.setdefault(entry.country, []).append(
            ProviderEntry(
                provider_name=entry.provider_name,
                logo_path=entry.logo_path,
                kind=entry.kind,
                url=click_out_url(entry.provider_name, title.name, entry.link),
            )
        )
    for country in availability:
        availability[country].sort(key=lambda e: (e.kind != "stream", e.provider_name))

    detail = TitleDetail(
        id=str(title.id),
        tmdb_id=title.tmdb_id,
        type=title.type,
        name=title.name,
        original_name=title.original_name,
        year=title.year,
        overview=title.overview,
        original_language=title.original_language,
        runtime=title.runtime,
        genres=title.genres or [],
        keywords=title.keywords or [],
        poster_path=title.poster_path,
        backdrop_path=title.backdrop_path,
        tmdb_rating=title.tmdb_rating,
        tmdb_votes=title.tmdb_votes,
        imdb_rating=title.imdb_rating,
        rt_score=title.rt_score,
        metacritic=title.metacritic,
        trailer_youtube_key=_trailer_key(title.raw_tmdb),
        cast=_cast(title.raw_tmdb),
        availability=availability,
        countries=countries,
        director=(title.raw_tmdb or {}).get("director"),
        country=(title.raw_tmdb or {}).get("country"),
        rated=(title.raw_tmdb or {}).get("rated"),
        certifications=title.certifications or {},
        certification=_certification_for(title, user),
        collection_id=title.collection_id,
        collection_name=title.collection_name,
        awards=(title.raw_tmdb or {}).get("awards"),
        imdb_id=title.imdb_id,
    )
    from app.ai import taste as taste_module

    scores = await taste_module.match_scores(db, user, [title.id])
    detail.match = scores.get(title.id)
    await db.commit()
    return detail
