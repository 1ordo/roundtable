"""TMDB client with Postgres-backed caching and quota accounting.

Every network call is counted in quota_usage. List-shaped responses are cached
in api_cache with per-endpoint TTLs; title details live on the titles table."""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import quota
from app.catalog.cache import cache_get, cache_put
from app.config import get_settings
from app.models import ApiCache

BASE = "https://api.themoviedb.org/3"

TRENDING_TTL = timedelta(hours=12)
LIST_TTL = timedelta(hours=24)
SEARCH_TTL = timedelta(hours=24)
GENRES_TTL = timedelta(days=30)
# A season that finished airing never changes; one that is airing gains an
# episode a week. Six hours is often enough to catch an episode on the day
# it lands without asking TMDB about Breaking Bad twice an hour.
SEASON_TTL = timedelta(hours=6)


class TmdbNotConfigured(Exception):
    pass


class TmdbError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


async def _http_get(db: AsyncSession, path: str, params: dict[str, Any] | None = None) -> dict:
    settings = get_settings()
    if not settings.tmdb_configured:
        raise TmdbNotConfigured("TMDB API key is not configured")

    merged = dict(params or {})
    headers = {}
    if settings.tmdb_access_token:
        headers["Authorization"] = f"Bearer {settings.tmdb_access_token}"
    else:
        merged["api_key"] = settings.tmdb_api_key

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(f"{BASE}{path}", params=merged, headers=headers)
    await quota.bump(db, "tmdb")
    if resp.status_code == 401:
        # The key is present but TMDB will not accept it: usually a key that
        # has not been activated yet. Say so rather than blaming the network.
        raise TmdbNotConfigured(
            "TMDB rejected the credentials. Check the key is active at "
            "themoviedb.org, Settings, API."
        )
    if resp.status_code != 200:
        raise TmdbError(f"TMDB {path} returned {resp.status_code}")
    return resp.json()


async def _cached_get(
    db: AsyncSession, path: str, params: dict[str, Any] | None, ttl: timedelta
) -> dict:
    plain = {k: v for k, v in (params or {}).items()}
    key = f"tmdb:{path}?" + "&".join(f"{k}={plain[k]}" for k in sorted(plain))
    row = (await db.execute(select(ApiCache).where(ApiCache.key == key))).scalar_one_or_none()
    if row is not None:
        fetched = row.fetched_at
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=UTC)
        if _now() - fetched < ttl:
            return row.payload

    payload = await _http_get(db, path, params)
    stmt = pg_insert(ApiCache).values(key=key, source="tmdb", payload=payload, fetched_at=_now())
    stmt = stmt.on_conflict_do_update(
        index_elements=[ApiCache.key], set_={"payload": payload, "fetched_at": _now()}
    )
    await db.execute(stmt)
    return payload


async def trending(db: AsyncSession, media_type: str, window: str = "week") -> dict:
    return await _cached_get(db, f"/trending/{media_type}/{window}", None, TRENDING_TTL)


async def discover(db: AsyncSession, media_type: str, params: dict[str, Any]) -> dict:
    return await _cached_get(db, f"/discover/{media_type}", params, LIST_TTL)


async def search_multi(db: AsyncSession, query: str, page: int = 1) -> dict:
    params = {"query": query, "page": page, "include_adult": "false"}
    return await _cached_get(db, "/search/multi", params, SEARCH_TTL)


async def genres(db: AsyncSession, media_type: str) -> dict:
    return await _cached_get(db, f"/genre/{media_type}/list", None, GENRES_TTL)


async def now_playing(db: AsyncSession, region: str | None = None, page: int = 1) -> dict:
    params: dict[str, Any] = {"page": page}
    if region:
        params["region"] = region
    return await _cached_get(db, "/movie/now_playing", params, LIST_TTL)


async def upcoming(db: AsyncSession, region: str | None = None, page: int = 1) -> dict:
    params: dict[str, Any] = {"page": page}
    if region:
        params["region"] = region
    return await _cached_get(db, "/movie/upcoming", params, LIST_TTL)


async def on_the_air(db: AsyncSession) -> dict:
    return await _cached_get(db, "/tv/on_the_air", None, LIST_TTL)


async def provider_list(db: AsyncSession, country: str) -> dict:
    params = {"watch_region": country}
    return await _cached_get(db, "/watch/providers/movie", params, GENRES_TTL)


async def details(db: AsyncSession, media_type: str, tmdb_id: int) -> dict:
    """Full detail payload, uncached here: the titles table is the cache."""
    # release_dates and content_ratings carry the official age ratings.
    append = "credits,keywords,videos,external_ids,watch/providers"
    append += ",release_dates" if media_type == "movie" else ",content_ratings"
    return await _http_get(db, f"/{media_type}/{tmdb_id}", {"append_to_response": append})


async def season(db: AsyncSession, tmdb_id: int, season_number: int) -> dict:
    """Every episode of one season, with air dates.

    Cached, unlike details: this is called for every season of every show
    anyone follows, on a schedule, so an uncached version would be the most
    expensive thing in the app.
    """
    return await _cached_get(db, f"/tv/{tmdb_id}/season/{season_number}", None, SEASON_TTL)


async def find_by_imdb(db: AsyncSession, imdb_id: str) -> dict | None:
    """Resolve an IMDb id to a TMDB record, so titles first learned from
    OMDb can be upgraded to the richer source."""
    payload = await _cached_get(db, f"/find/{imdb_id}", {"external_source": "imdb_id"}, GENRES_TTL)
    for key, media_type in (("movie_results", "movie"), ("tv_results", "tv")):
        results = payload.get(key) or []
        if results:
            return {"media_type": media_type, **results[0]}
    return None


async def best_match(db: AsyncSession, name: str) -> dict | None:
    """The most plausible TMDB record for a title name."""
    payload = await search_multi(db, name)
    candidates = [
        item for item in payload.get("results", []) if item.get("media_type") in ("movie", "tv")
    ]
    if not candidates:
        return None
    # TMDB orders by relevance already; prefer an exact name match when one
    # exists, then fall back to the top hit.
    lowered = name.strip().lower()
    for item in candidates:
        title = (item.get("title") or item.get("name") or "").lower()
        if title == lowered:
            return item
    return candidates[0]


async def collection(db: AsyncSession, collection_id: int) -> dict:
    """Every part of a franchise, in release order."""
    return await _cached_get(db, f"/collection/{collection_id}", None, GENRES_TTL)


async def person(db: AsyncSession, person_id: int) -> dict:
    """One person, with everything they are known for."""
    return await _cached_get(
        db,
        f"/person/{person_id}",
        {"append_to_response": "combined_credits,external_ids"},
        GENRES_TTL,
    )


async def countries(db: AsyncSession) -> list[dict]:
    """Every country the provider knows, for the region picker."""
    # This endpoint answers with a bare list, so it is wrapped for the cache
    # and unwrapped on the way out.
    cached = await cache_get(db, "tmdb:countries", 24 * 30)
    if cached is not None:
        return cached.get("countries", [])
    raw = await _http_get(db, "/configuration/countries", {"language": "en-US"})
    countries_list = raw if isinstance(raw, list) else raw.get("results", [])
    await cache_put(db, "tmdb:countries", {"countries": countries_list})
    return countries_list
