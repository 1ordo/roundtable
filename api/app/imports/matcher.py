"""Deterministic TMDB matching for import rows.

Confidence rules, in order:
- exact case-insensitive name match (plus year within one, when known): auto
- a single search result of the right type: auto
- otherwise: ambiguous, top candidates go to the review queue
The AI milestone can add LLM-assisted disambiguation on top; this layer stays
reproducible without it."""

import unicodedata
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import tmdb


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    return " ".join(value.lower().split())


def _candidate(item: dict) -> dict[str, Any]:
    media_type = item.get("media_type")
    date = item.get("release_date") if media_type == "movie" else item.get("first_air_date")
    return {
        "tmdb_id": item["id"],
        "type": media_type,
        "name": item.get("title") or item.get("name") or "Untitled",
        "year": int(date[:4]) if date and date[:4].isdigit() else None,
        "poster_path": item.get("poster_path"),
        "popularity": item.get("popularity") or 0,
    }


async def match_row(
    db: AsyncSession, name: str, type_hint: str | None, year: int | None
) -> tuple[str, list[dict]]:
    """Return (status, candidates); status is matched | ambiguous | unmatched.
    When matched, candidates[0] is the pick."""
    payload = await tmdb.search_multi(db, name)
    results = [
        _candidate(item)
        for item in payload.get("results", [])
        if item.get("media_type") in ("movie", "tv")
    ]
    if type_hint:
        typed = [c for c in results if c["type"] == type_hint]
        if typed:
            results = typed
    if not results:
        return "unmatched", []

    target = _norm(name)
    exact = [c for c in results if _norm(c["name"]) == target]
    if year is not None:
        with_year = [c for c in exact if c["year"] is not None and abs(c["year"] - year) <= 1]
        if len(with_year) == 1:
            return "matched", with_year
        if len(with_year) > 1:
            return "ambiguous", with_year[:5]
    if len(exact) == 1:
        return "matched", exact
    if len(exact) > 1:
        # Same name, several titles (remakes): the most popular usually wins,
        # but that guess is exactly what the review queue is for.
        return "ambiguous", sorted(exact, key=lambda c: -c["popularity"])[:5]
    if len(results) == 1:
        return "matched", results
    return "ambiguous", sorted(results, key=lambda c: -c["popularity"])[:5]
