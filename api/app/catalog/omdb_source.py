"""OMDb as a full catalog source.

TMDB is the richer provider, but it needs a working key. OMDb only needs the
free key and still returns real titles, posters, plots, genres, languages and
ratings, so the app has a genuine catalog either way. Everything fetched here
is cached in Postgres and reused; the daily budget is respected.
"""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import quota
from app.catalog.cache import cache_get, cache_put
from app.config import get_settings
from app.models import Title

logger = logging.getLogger("watchpile.omdb")

BASE = "https://www.omdbapi.com/"
SEARCH_TTL_HOURS = 24 * 7
DETAIL_TTL_HOURS = 24 * 30

# OMDb reports genres as names. Map to the TMDB ids the rest of the app uses
# so genre rows, filters and onboarding keep one vocabulary.
GENRE_IDS = {
    "Action": 28,
    "Adventure": 12,
    "Animation": 16,
    "Biography": 36,
    "Comedy": 35,
    "Crime": 80,
    "Documentary": 99,
    "Drama": 18,
    "Family": 10751,
    "Fantasy": 14,
    "History": 36,
    "Horror": 27,
    "Music": 10402,
    "Musical": 10402,
    "Mystery": 9648,
    "Romance": 10749,
    "Sci-Fi": 878,
    "Sport": 99,
    "Thriller": 53,
    "War": 10752,
    "Western": 37,
}

LANGUAGE_CODES = {
    "english": "en",
    "arabic": "ar",
    "french": "fr",
    "spanish": "es",
    "japanese": "ja",
    "korean": "ko",
    "german": "de",
    "italian": "it",
    "hindi": "hi",
    "turkish": "tr",
    "portuguese": "pt",
    "mandarin": "zh",
    "chinese": "zh",
    "russian": "ru",
    "persian": "fa",
    "hebrew": "he",
    "swedish": "sv",
    "danish": "da",
    "norwegian": "no",
    "polish": "pl",
    "dutch": "nl",
    "thai": "th",
}


class OmdbNotConfigured(Exception):
    pass


class OmdbError(Exception):
    pass


def configured() -> bool:
    return bool(get_settings().omdb_api_key)


async def _get(db: AsyncSession, params: dict, ttl_hours: int) -> dict:
    settings = get_settings()
    if not settings.omdb_api_key:
        raise OmdbNotConfigured("OMDb API key is not configured")

    cache_key = "omdb:" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    cached = await cache_get(db, cache_key, ttl_hours)
    if cached is not None:
        return cached

    if await quota.used_today(db, "omdb") >= settings.omdb_daily_budget:
        raise OmdbError("daily OMDb budget reached")

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(BASE, params={"apikey": settings.omdb_api_key, **params})
    except httpx.HTTPError as exc:
        raise OmdbError(str(exc)) from exc
    await quota.bump(db, "omdb")
    if resp.status_code != 200:
        raise OmdbError(f"OMDb returned {resp.status_code}")
    payload = resp.json()
    if payload.get("Response") != "True":
        # "Movie not found" is a valid, cacheable answer.
        payload = {"Response": "False", "Error": payload.get("Error", "not found")}
    await cache_put(db, cache_key, payload)
    return payload


async def search(db: AsyncSession, term: str, page: int = 1) -> list[dict]:
    payload = await _get(db, {"s": term, "page": page}, SEARCH_TTL_HOURS)
    return payload.get("Search", []) or []


async def detail_by_id(db: AsyncSession, imdb_id: str) -> dict | None:
    payload = await _get(db, {"i": imdb_id, "plot": "full"}, DETAIL_TTL_HOURS)
    return payload if payload.get("Response") == "True" else None


async def detail_by_title(db: AsyncSession, name: str, year: int | None = None) -> dict | None:
    params: dict = {"t": name, "plot": "full"}
    if year:
        params["y"] = year
    payload = await _get(db, params, DETAIL_TTL_HOURS)
    return payload if payload.get("Response") == "True" else None


def _year_or_none(raw: str | None) -> int | None:
    """Series report a run like "2008-2013"; the start year is the one to
    show, so take the first four digits rather than every digit."""
    if not raw or raw == "N/A":
        return None
    digits = ""
    for char in raw:
        if char.isdigit():
            digits += char
            if len(digits) == 4:
                return int(digits)
        elif digits:
            break
    return int(digits) if digits else None


def _int_or_none(raw: str | None) -> int | None:
    if not raw or raw == "N/A":
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    return int(digits) if digits else None


def _poster(raw: str | None) -> str | None:
    if not raw or raw == "N/A":
        return None
    # OMDb posters are absolute Amazon URLs. Ask for a larger render than the
    # default 300px so cards stay sharp.
    return raw.replace("._V1_SX300", "._V1_SX600").replace("_UX380_", "_UX600_")


def genres_from(raw: str | None) -> list[dict]:
    if not raw or raw == "N/A":
        return []
    out = []
    seen = set()
    for name in [g.strip() for g in raw.split(",")]:
        gid = GENRE_IDS.get(name)
        if gid is None or gid in seen:
            continue
        seen.add(gid)
        out.append({"id": gid, "name": "Science fiction" if name == "Sci-Fi" else name})
    return out


def language_of(raw: str | None) -> str | None:
    if not raw or raw == "N/A":
        return None
    first = raw.split(",")[0].strip().lower()
    return LANGUAGE_CODES.get(first, first[:2])


def keywords_from(data: dict) -> list[str]:
    """Cast, director and country double as retrieval keywords: they are what
    people actually search and what the embedding text needs."""
    words: list[str] = []
    for field in ("Director", "Writer", "Actors", "Country"):
        value = data.get(field, "")
        if value and value != "N/A":
            words.extend(part.strip() for part in value.split(",")[:4])
    return [w for w in words if w][:16]


def imdb_numeric_id(imdb_id: str) -> int:
    """Stable positive integer id derived from the IMDb id, used as the
    tmdb_id surrogate so one table serves both providers."""
    return int(imdb_id.replace("tt", "").lstrip("0") or "0")


async def upsert_from_omdb(db: AsyncSession, data: dict) -> Title | None:
    imdb_id = data.get("imdbID")
    if not imdb_id:
        return None
    kind = "tv" if data.get("Type") == "series" else "movie"
    surrogate = imdb_numeric_id(imdb_id)

    # One IMDb id can match several rows: a movie/series pair sharing the
    # id, or a TMDB-native row next to the surrogate shadow this function
    # created before the native one arrived. Pick deterministically — same
    # kind first, and a native row outranks the surrogate — rather than
    # crashing the whole ingest on the first film that has both.
    rows = (
        (await db.execute(select(Title).where(Title.imdb_id == imdb_id).order_by(Title.id)))
        .scalars()
        .all()
    )
    title = None
    if rows:
        same_kind = [t for t in rows if t.type == kind] or rows
        title = next((t for t in same_kind if t.tmdb_id != surrogate), same_kind[0])
    if title is None:
        title = (
            await db.execute(select(Title).where(Title.tmdb_id == surrogate, Title.type == kind))
        ).scalar_one_or_none()
    if title is None:
        title = Title(tmdb_id=surrogate, type=kind, name=data.get("Title", "Untitled"))
        db.add(title)

    title.imdb_id = imdb_id
    title.name = data.get("Title") or title.name
    title.original_name = title.original_name or title.name
    title.year = _year_or_none(data.get("Year"))
    title.runtime = _int_or_none(data.get("Runtime"))
    title.overview = None if data.get("Plot") in (None, "N/A") else data["Plot"]
    title.original_language = language_of(data.get("Language"))
    title.genres = genres_from(data.get("Genre"))
    title.keywords = keywords_from(data)
    title.poster_path = _poster(data.get("Poster"))
    title.details_refreshed_at = datetime.now(UTC)
    title.raw_tmdb = {
        "source": "omdb",
        "credits": {
            "cast": [
                {"name": n.strip(), "character": "", "profile_path": None}
                for n in (data.get("Actors", "") or "").split(",")
                if n.strip() and n.strip() != "N/A"
            ]
        },
        "director": data.get("Director"),
        "country": data.get("Country"),
        "rated": data.get("Rated"),
        "awards": data.get("Awards"),
        "released": data.get("Released"),
        "videos": {"results": []},
    }

    with contextlib.suppress(ValueError, TypeError):
        if data.get("imdbRating") and data["imdbRating"] != "N/A":
            title.imdb_rating = float(data["imdbRating"])
            # One 0-10 number drives the card badges regardless of provider.
            title.tmdb_rating = title.imdb_rating
    votes = _int_or_none(data.get("imdbVotes"))
    if votes:
        title.tmdb_votes = votes
        # Vote count is the only popularity signal OMDb gives.
        title.popularity = round(votes / 1000, 2)
    if data.get("Metascore") and data["Metascore"] != "N/A":
        with contextlib.suppress(ValueError, TypeError):
            title.metacritic = int(data["Metascore"])
    for rating in data.get("Ratings", []) or []:
        if rating.get("Source") == "Rotten Tomatoes":
            with contextlib.suppress(ValueError, TypeError):
                title.rt_score = int(rating.get("Value", "").rstrip("%"))
    title.scores_refreshed_at = datetime.now(UTC)

    await db.flush()
    return title


async def ensure_by_imdb_id(db: AsyncSession, imdb_id: str) -> Title | None:
    data = await detail_by_id(db, imdb_id)
    if data is None:
        return None
    return await upsert_from_omdb(db, data)


async def import_titles(db: AsyncSession, names: list[str], pause: float = 0.0) -> int:
    """Resolve a list of real titles and store them. Used to bootstrap the
    catalog; every call is cached so reruns are free."""
    added = 0
    for name in names:
        try:
            data = await detail_by_title(db, name)
        except (OmdbError, OmdbNotConfigured) as exc:
            logger.warning("stopping import: %s", exc)
            break
        if data is None:
            logger.info("no OMDb match for %s", name)
            continue
        title = await upsert_from_omdb(db, data)
        if title is not None:
            added += 1
        if pause:
            await asyncio.sleep(pause)
    await db.commit()
    return added
