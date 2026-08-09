"""Turn TMDB detail payloads into titles and availability rows."""

import contextlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import omdb_source, tmdb
from app.models import Availability, Title

DETAILS_TTL = timedelta(hours=24)

KIND_MAP = {
    "flatrate": "stream",
    "rent": "rent",
    "buy": "buy",
    "ads": "ads",
    "free": "free",
}


def _year_from(date_str: str | None) -> int | None:
    if date_str and len(date_str) >= 4 and date_str[:4].isdigit():
        return int(date_str[:4])
    return None


def _extract_keywords(media_type: str, payload: dict) -> list[str]:
    block = payload.get("keywords") or {}
    items = block.get("keywords") if media_type == "movie" else block.get("results")
    return [k["name"] for k in (items or []) if k.get("name")]


def _extract_imdb_id(payload: dict) -> str | None:
    return payload.get("imdb_id") or (payload.get("external_ids") or {}).get("imdb_id")


def _extract_runtime(media_type: str, payload: dict) -> int | None:
    if media_type == "movie":
        return payload.get("runtime") or None
    runtimes = payload.get("episode_run_time") or []
    return runtimes[0] if runtimes else None


def extract_certifications(media_type: str, payload: dict) -> dict[str, str]:
    """Official age ratings per country, straight from the provider.

    Nothing is inferred here: a country missing from this map means we have
    no rating for it, which is different from being unrated."""
    out: dict[str, str] = {}
    if media_type == "movie":
        for entry in (payload.get("release_dates") or {}).get("results", []):
            country = entry.get("iso_3166_1")
            for release in entry.get("release_dates", []):
                cert = (release.get("certification") or "").strip()
                if country and cert:
                    out.setdefault(country, cert)
    else:
        for entry in (payload.get("content_ratings") or {}).get("results", []):
            country = entry.get("iso_3166_1")
            cert = (entry.get("rating") or "").strip()
            if country and cert:
                out.setdefault(country, cert)
    return out


def apply_details(title: Title, media_type: str, payload: dict) -> None:
    if media_type == "movie":
        title.name = payload.get("title") or payload.get("original_title") or "Untitled"
        title.original_name = payload.get("original_title")
        title.year = _year_from(payload.get("release_date"))
    else:
        title.name = payload.get("name") or payload.get("original_name") or "Untitled"
        title.original_name = payload.get("original_name")
        title.year = _year_from(payload.get("first_air_date"))
    title.overview = (payload.get("overview") or "")[:8000] or None
    title.original_language = payload.get("original_language")
    title.runtime = _extract_runtime(media_type, payload)
    title.genres = payload.get("genres") or []
    title.keywords = _extract_keywords(media_type, payload)
    title.poster_path = payload.get("poster_path")
    title.backdrop_path = payload.get("backdrop_path")
    title.popularity = payload.get("popularity")
    title.tmdb_rating = payload.get("vote_average")
    title.tmdb_votes = payload.get("vote_count")
    title.imdb_id = _extract_imdb_id(payload)
    title.certifications = extract_certifications(media_type, payload)
    collection = payload.get("belongs_to_collection") or {}
    title.collection_id = collection.get("id")
    title.collection_name = collection.get("name")
    title.raw_tmdb = payload
    title.details_refreshed_at = datetime.now(UTC)


async def sync_availability(db: AsyncSession, title: Title, payload: dict) -> None:
    """Upsert provider rows for every country TMDB reports. Rows keep their
    first_seen_at; last_seen_at moves forward on every sync so the milestone 5
    differ can spot both arrivals and departures."""
    results = (payload.get("watch/providers") or {}).get("results") or {}
    now = datetime.now(UTC)
    existing = {
        (a.country, a.provider_id, a.kind): a
        for a in (
            await db.execute(select(Availability).where(Availability.title_id == title.id))
        ).scalars()
    }
    for country, block in results.items():
        if len(country) != 2:
            continue
        link = block.get("link")
        for tmdb_kind, kind in KIND_MAP.items():
            for provider in block.get(tmdb_kind) or []:
                pid = provider.get("provider_id")
                if pid is None:
                    continue
                row = existing.get((country, pid, kind))
                if row is None:
                    row = Availability(
                        title_id=title.id,
                        country=country,
                        provider_id=pid,
                        provider_name=provider.get("provider_name") or "Unknown",
                        logo_path=provider.get("logo_path"),
                        kind=kind,
                        link=link,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                    db.add(row)
                    existing[(country, pid, kind)] = row
                else:
                    row.provider_name = provider.get("provider_name") or row.provider_name
                    row.logo_path = provider.get("logo_path") or row.logo_path
                    row.link = link or row.link
                    row.last_seen_at = now
    await db.flush()


def _is_stale(title: Title) -> bool:
    if title.details_refreshed_at is None:
        return True
    refreshed = title.details_refreshed_at
    if refreshed.tzinfo is None:
        refreshed = refreshed.replace(tzinfo=UTC)
    return datetime.now(UTC) - refreshed > DETAILS_TTL


async def ingest_popular(db: AsyncSession, pages: int = 2) -> int:
    """Pull the current most popular titles into the local catalog so the
    embedding corpus is wider than what people happened to click."""
    ingested = 0
    for media_type in ("movie", "tv"):
        for page in range(1, pages + 1):
            payload = await tmdb.discover(
                db,
                media_type,
                {"sort_by": "popularity.desc", "page": page, "vote_count.gte": 100},
            )
            for item in payload.get("results", []):
                await ensure_title(db, media_type, item["id"])
                ingested += 1
            await db.commit()
    return ingested


async def ensure_title(
    db: AsyncSession, media_type: str, tmdb_id: int, force: bool = False
) -> Title:
    """Return the local row for a TMDB title, fetching or refreshing it when
    missing or older than a day. The titles table is the detail cache."""
    title = (
        await db.execute(select(Title).where(Title.tmdb_id == tmdb_id, Title.type == media_type))
    ).scalar_one_or_none()

    if title is not None and not force and not _is_stale(title):
        return title

    try:
        payload = await tmdb.details(db, media_type, tmdb_id)
    except (tmdb.TmdbError, tmdb.TmdbNotConfigured):
        # Serve what we already hold rather than fail.
        if title is not None:
            # Refresh through OMDb when it is the active source, so ratings
            # and plots still stay current without TMDB.
            if title.imdb_id and omdb_source.configured():
                with contextlib.suppress(omdb_source.OmdbError, omdb_source.OmdbNotConfigured):
                    data = await omdb_source.detail_by_id(db, title.imdb_id)
                    if data is not None:
                        await omdb_source.upsert_from_omdb(db, data)
            return title
        raise

    if title is None:
        title = Title(tmdb_id=tmdb_id, type=media_type, name="Untitled")
        db.add(title)
    apply_details(title, media_type, payload)
    await db.flush()
    await sync_availability(db, title, payload)

    # The catalog grows as people browse, so give every new title its vector
    # right away: whatever you just opened can be recommended from now on.
    from app.ai import embeddings as embeddings_module

    await embeddings_module.embed_title_now(db, title)
    return title
