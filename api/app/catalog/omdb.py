"""OMDb client for IMDb, Rotten Tomatoes, and Metacritic scores.

The free tier allows 1000 requests per day, so scores are cached permanently
on the title and refreshed at most monthly, guarded by a daily budget."""

import contextlib
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import quota
from app.config import get_settings
from app.models import Title

BASE = "https://www.omdbapi.com/"
REFRESH_AFTER = timedelta(days=30)


def needs_refresh(title: Title) -> bool:
    if not title.imdb_id:
        return False
    if title.scores_refreshed_at is None:
        return True
    refreshed = title.scores_refreshed_at
    if refreshed.tzinfo is None:
        refreshed = refreshed.replace(tzinfo=UTC)
    return datetime.now(UTC) - refreshed > REFRESH_AFTER


async def fetch_scores(db: AsyncSession, imdb_id: str) -> dict | None:
    settings = get_settings()
    if not settings.omdb_api_key:
        return None
    if await quota.used_today(db, "omdb") >= settings.omdb_daily_budget:
        return None
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(BASE, params={"apikey": settings.omdb_api_key, "i": imdb_id})
    await quota.bump(db, "omdb")
    if resp.status_code != 200:
        return None
    data = resp.json()
    if data.get("Response") != "True":
        return None
    return data


def apply_scores(title: Title, data: dict) -> None:
    with contextlib.suppress(ValueError, TypeError):
        if data.get("imdbRating") and data["imdbRating"] != "N/A":
            title.imdb_rating = float(data["imdbRating"])
    if data.get("Metascore") and data["Metascore"] != "N/A":
        with contextlib.suppress(ValueError, TypeError):
            title.metacritic = int(data["Metascore"])
    for rating in data.get("Ratings", []):
        if rating.get("Source") == "Rotten Tomatoes":
            value = rating.get("Value", "").rstrip("%")
            with contextlib.suppress(ValueError, TypeError):
                title.rt_score = int(value)
    title.scores_refreshed_at = datetime.now(UTC)


async def refresh_title_scores(db: AsyncSession, title: Title) -> None:
    """Best effort: score gaps must never break a detail page."""
    if not needs_refresh(title):
        return
    try:
        data = await fetch_scores(db, title.imdb_id or "")
    except httpx.HTTPError:
        return
    if data is not None:
        apply_scores(title, data)
