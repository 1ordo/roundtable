"""What to watch, in what order, for a franchise.

Answers "the Marvel films from A to Z", "Harry Potter", and "what leads into
the last Spider-Man". None of it is a language model's job: the catalog
knows the answer, and a model asked to list a franchise returns a plausible
order with entries missing. The model's only role is recognising that the
question was asked; everything below is deterministic and testable.

Three strategies, in order:

  UNIVERSE   A registry entry (app.catalog.universes) for franchises that
             are bigger than one TMDB collection. The MCU is the reason
             this exists: it is not a collection, it is a keyword and a
             studio.
  COLLECTION TMDB's own grouping, which covers most of what people ask for:
             Harry Potter, each Spider-Man series, every ordinary sequel run.
  ANCHOR     Start from a title someone named, take its collection, and
             widen to the universe around it if it belongs to one.

Ordering is always by full release date, never by year. Franchises that
ship one film a year hide the difference; the MCU shipped four in 2021, and
ordering those by year gives a random order within it.
"""

import logging
import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import tmdb, universes
from app.models import Title, User, WatchEvent

logger = logging.getLogger("roundtable.watch_order")

# TMDB pages 20 at a time and the MCU is around 60 entries across films and
# series. Five pages each is plenty and bounds the cost of a bad query.
MAX_PAGES = 5
PER_PAGE = 20

# The most a resolve() can hand back: five pages of twenty, for films and
# again for series. Anything that consumes a watch order has to accept at
# least this many.
#
# This constant exists because it did not. The save endpoint capped a request
# at sixty, the Marvel Cinematic Universe resolves to seventy-two, and so the
# assistant offered a button that could not work for the one franchise people
# ask for by name. Two ceilings that have to agree should not be two numbers
# typed in two files.
MAX_TITLES = MAX_PAGES * PER_PAGE * 2


@dataclass
class OrderedTitle:
    tmdb_id: int
    type: str
    name: str
    year: int | None
    release_date: date | None
    poster_path: str | None
    overview: str | None
    watched: bool = False


@dataclass
class WatchOrder:
    name: str
    kind: str  # universe | collection | anchor
    titles: list[OrderedTitle]
    note: str = ""

    @property
    def unwatched(self) -> list[OrderedTitle]:
        return [t for t in self.titles if not t.watched]


def _as_date(value: object) -> date | None:
    text = str(value or "")[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _from_tmdb(item: dict, media_type: str) -> OrderedTitle | None:
    tmdb_id = item.get("id")
    name = item.get("title") or item.get("name")
    if not tmdb_id or not name:
        return None
    released = _as_date(item.get("release_date") or item.get("first_air_date"))
    return OrderedTitle(
        tmdb_id=int(tmdb_id),
        type=media_type,
        name=str(name),
        year=released.year if released else None,
        release_date=released,
        poster_path=item.get("poster_path"),
        overview=item.get("overview") or None,
    )


def _bare_name(name: str) -> str:
    """A collection name with TMDB's bookkeeping word removed."""
    return " ".join(re.sub(r"\s*collection\s*$", "", name or "", flags=re.I).lower().split())


def _exact_match(query: str, candidates: list[tuple[int, str]]) -> int | None:
    """The collection whose name IS the thing asked for, if one of them is.

    Asked for "star wars", the local table answered with whichever row a
    substring match happened to reach first, which was The Ewok Adventures
    Collection: two television films from 1984. Asked for "batman" it
    answered The Batman Collection, a single film from 2022. Both are
    honest substring matches and neither is the franchise anybody meant.

    So a local row is only trusted when its name is exactly what was asked
    for. Anything less goes to the search engine, which ranks these
    correctly and is one call away.
    """
    wanted = " ".join((query or "").lower().split())
    if not wanted:
        return None
    for collection_id, name in candidates:
        if _bare_name(name) == wanted:
            return collection_id
    return None


def _sorted(titles: list[OrderedTitle]) -> list[OrderedTitle]:
    """Release order. Anything undated sorts last rather than first, because
    an unreleased entry is not where a watch-through starts."""
    return sorted(titles, key=lambda t: (t.release_date is None, t.release_date or date.max))


async def _discover_universe(db: AsyncSession, universe: universes.Universe) -> list[OrderedTitle]:
    """Every feature in a franchise defined by keyword and studio."""
    out: list[OrderedTitle] = []
    media_types = ["movie", "tv"] if universe.include_tv else ["movie"]

    for media_type in media_types:
        for page in range(1, MAX_PAGES + 1):
            params: dict[str, object] = {
                "page": page,
                "sort_by": "primary_release_date.asc"
                if media_type == "movie"
                else "first_air_date.asc",
                "include_adult": "false",
            }
            if universe.keywords:
                params["with_keywords"] = "|".join(str(k) for k in universe.keywords)
            if universe.companies and media_type == "movie":
                params["with_companies"] = "|".join(str(c) for c in universe.companies)
            if universe.without_genres:
                params["without_genres"] = ",".join(str(g) for g in universe.without_genres)
            # Runtime filtering only exists for films; a series episode
            # runtime says nothing useful about whether it is a special.
            if universe.min_runtime and media_type == "movie":
                params["with_runtime.gte"] = universe.min_runtime

            try:
                payload = await tmdb.discover(db, media_type, params)
            except (tmdb.TmdbNotConfigured, tmdb.TmdbError):
                logger.info("discover unavailable for %s page %s", universe.key, page)
                break

            results = payload.get("results") or []
            for item in results:
                found = _from_tmdb(item, media_type)
                if found is not None:
                    out.append(found)
            if page >= int(payload.get("total_pages") or 1):
                break
    return out


async def _collection_titles(
    db: AsyncSession, collection_id: int
) -> tuple[str, list[OrderedTitle]]:
    payload = await tmdb.collection(db, collection_id)
    parts = [
        found
        for found in (_from_tmdb(item, "movie") for item in payload.get("parts") or [])
        if found is not None
    ]
    return str(payload.get("name") or "This franchise"), parts


async def _mark_watched(db: AsyncSession, user: User, titles: list[OrderedTitle]) -> None:
    """Fill in what this person has already seen, in one query."""
    if not titles:
        return
    ids = [t.tmdb_id for t in titles]
    rows = (
        await db.execute(
            select(Title.tmdb_id, Title.type)
            .join(WatchEvent, WatchEvent.title_id == Title.id)
            .where(WatchEvent.user_id == user.id, Title.tmdb_id.in_(ids))
        )
    ).all()
    seen = {(tmdb_id, kind) for tmdb_id, kind in rows}
    for title in titles:
        title.watched = (title.tmdb_id, title.type) in seen


async def resolve(
    db: AsyncSession,
    query: str | None = None,
    tmdb_id: int | None = None,
    media_type: str = "movie",
    user: User | None = None,
) -> WatchOrder | None:
    """A franchise name, or a title, to an ordered watch-through.

    Returns None when nothing matched, which the caller should treat as "I
    do not know this franchise" rather than as an error.
    """
    # 1. A franchise too big to be a collection.
    if query:
        universe = universes.find(query)
        if universe is not None:
            titles = _sorted(await _discover_universe(db, universe))
            if titles:
                if user is not None:
                    await _mark_watched(db, user, titles)
                return WatchOrder(
                    name=universe.name, kind="universe", titles=titles, note=universe.note
                )

    # 2. A TMDB collection, checked locally first so a catalog we already
    #    have does not cost a search, but only on an exact name.
    if query:
        local = (
            (
                await db.execute(
                    select(Title.collection_id, Title.collection_name)
                    .where(
                        Title.collection_id.is_not(None),
                        Title.collection_name.ilike(f"%{query.strip()}%"),
                    )
                    .distinct()
                    .limit(25)
                )
            )
            .tuples()
            .all()
        )
        collection_id = _exact_match(
            query, [(row[0], row[1] or "") for row in local if row[0] is not None]
        )
        if collection_id is None:
            try:
                results = (await tmdb.search_collection(db, query)).get("results") or []
                named = [(int(r["id"]), str(r.get("name") or "")) for r in results if r.get("id")]
                # Prefer the one actually called this; otherwise TMDB's own
                # ranking, which puts the canonical collection first.
                collection_id = _exact_match(query, named) or (named[0][0] if named else None)
            except (tmdb.TmdbNotConfigured, tmdb.TmdbError):
                collection_id = None
        if collection_id:
            try:
                name, titles = await _collection_titles(db, int(collection_id))
            except (tmdb.TmdbNotConfigured, tmdb.TmdbError):
                return None
            titles = _sorted(titles)
            if titles:
                if user is not None:
                    await _mark_watched(db, user, titles)
                return WatchOrder(name=name, kind="collection", titles=titles)

    # 3. From a title someone named: its own series, widened to the universe
    #    it belongs to when it is part of one. This is the path for "what do
    #    I watch before the last Spider-Man".
    if tmdb_id is not None:
        title = (
            await db.execute(
                select(Title).where(Title.tmdb_id == tmdb_id, Title.type == media_type)
            )
        ).scalar_one_or_none()
        if title is None:
            return None

        raw = title.raw_tmdb or {}
        keyword_ids = {
            int(k.get("id"))
            for k in ((raw.get("keywords") or {}).get("keywords") or [])
            + ((raw.get("keywords") or {}).get("results") or [])
            if k.get("id") is not None
        }
        universe = universes.for_keyword_ids(keyword_ids)
        if universe is not None:
            titles = _sorted(await _discover_universe(db, universe))
            if titles:
                if user is not None:
                    await _mark_watched(db, user, titles)
                return WatchOrder(
                    name=universe.name,
                    kind="anchor",
                    titles=titles,
                    note=(
                        f"{title.name} is part of {universe.name}. This is the whole "
                        "thing in release order; there is no authoritative list of "
                        "what is strictly required first, so this errs toward more."
                    ),
                )
        if title.collection_id:
            try:
                name, found = await _collection_titles(db, int(title.collection_id))
            except (tmdb.TmdbNotConfigured, tmdb.TmdbError):
                return None
            found = _sorted(found)
            if found:
                if user is not None:
                    await _mark_watched(db, user, found)
                return WatchOrder(name=name, kind="anchor", titles=found)

    return None
