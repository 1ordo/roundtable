"""Natural-language search. The LLM only translates the query into structured
filters plus a mood description; candidate retrieval and ranking are done by
embeddings and plain filtering. The LLM never invents the result list."""

import logging
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import client, taste
from app.models import Availability, Title, User

logger = logging.getLogger("watchpile.ai")

PARSE_SYSTEM = """You translate a movie or series request into search filters.
The request can be in English, French, Arabic including darija, or mixed.
Reply with ONLY a JSON object with these keys:
- "mood": a one-sentence English description of the story vibe being asked for
- "genres": array of TMDB genre names in English (empty if unspecified)
- "types": array containing "movie", "tv", or both
- "runtime_max": integer minutes or null
- "year_from": integer year or null
- "year_to": integer year or null
- "on_shared_services": true when they ask for services both people have,
  false otherwise
Do not add other keys. Do not recommend titles."""

CANDIDATE_POOL = 300


def _passes_filters(title: Title, parsed: dict[str, Any]) -> bool:
    types = parsed.get("types") or []
    if types and title.type not in types:
        return False
    genres = {g.lower() for g in (parsed.get("genres") or [])}
    if genres:
        title_genres = {g.get("name", "").lower() for g in (title.genres or [])}
        if not title_genres & genres:
            return False
    runtime_max = parsed.get("runtime_max")
    if runtime_max and title.runtime and title.runtime > int(runtime_max):
        return False
    year_from = parsed.get("year_from")
    if year_from and title.year and title.year < int(year_from):
        return False
    year_to = parsed.get("year_to")
    return not (year_to and title.year and title.year > int(year_to))


async def _shared_service_title_ids(db: AsyncSession, user: User) -> set | None:
    """Titles streamable on services that every user with services subscribes
    to, in their own countries."""
    users = (await db.execute(select(User))).scalars().all()
    with_services = [u for u in users if u.services and u.country_code]
    if not with_services:
        return None
    allowed: set = set()
    first = True
    for member in with_services:
        rows = (
            await db.execute(
                select(Availability.title_id).where(
                    Availability.country == member.country_code,
                    Availability.provider_id.in_(member.services),
                    Availability.kind == "stream",
                )
            )
        ).scalars()
        member_titles = set(rows)
        allowed = member_titles if first else (allowed & member_titles)
        first = False
    return allowed


async def nl_search(db: AsyncSession, user: User, query: str) -> dict[str, Any]:
    parsed = await client.chat_json(db, PARSE_SYSTEM, query)
    mood = str(parsed.get("mood") or query)
    vectors = await client.embed_texts(db, [mood])
    mood_vector = np.array(vectors[0])

    ranked = await taste.rank_titles_by_vector(db, mood_vector, limit=CANDIDATE_POOL)

    shared_ids = None
    if parsed.get("on_shared_services"):
        shared_ids = await _shared_service_title_ids(db, user)

    results = []
    for title, score in ranked:
        if not _passes_filters(title, parsed):
            continue
        if shared_ids is not None and title.id not in shared_ids:
            continue
        results.append((title, score))
        if len(results) >= 24:
            break

    return {"parsed": parsed, "results": results}
