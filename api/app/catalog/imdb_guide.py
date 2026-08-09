"""The real parents guide, from IMDb.

The generated advisory in app/ai/advisories.py is an estimate from the plot
and the age rating. This is the actual thing: the five IMDb categories, each
with the severity people voted on and the itemised entries describing what
happens and where. That is the accuracy bar, and nothing derived from a
synopsis reaches it.

Two constraints shape the implementation:

  on demand    a guide is fetched the first time someone opens a title with
               the parents guide enabled, not swept for the whole catalog.
  cached hard  once fetched it is kept for a long time, because a guide for
               a released film barely changes and every request is a request
               against someone else's service.

IMDb attaches a disclaimer to this data: it is for limited non-commercial
use. A self-hosted instance for one household is that case. Anyone
deploying this publicly should turn it off.
"""

import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import cache
from app.models import Title

logger = logging.getLogger("watchpile.imdb_guide")

ENDPOINT = "https://api.graphql.imdb.com/"
TIMEOUT = 12.0
# A released title's guide is stable; a month is a fair compromise between
# picking up new entries and not hammering the source.
TTL_HOURS = 30 * 24

# The web client sends these; without them the endpoint refuses.
HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://www.imdb.com",
    "Referer": "https://www.imdb.com/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

QUERY = """
query ParentsGuide($id: ID!) {
  title(id: $id) {
    parentsGuide {
      categories {
        category { id text }
        severity { text }
        guideItems(first: 30) {
          total
          edges { node { text { plainText } isSpoiler } }
        }
      }
    }
  }
}
"""

# IMDb's category ids, mapped onto the keys the rest of the app already uses
# so the two sources are interchangeable in the UI. IMDb sends these
# uppercase; they are lowercased before lookup.
CATEGORY_KEYS = {
    "nudity": "sex_nudity",
    "violence": "violence",
    "profanity": "language",
    "alcohol": "substances",
    "frightening": "frightening",
}

LABELS = {
    "sex_nudity": "Sex and nudity",
    "violence": "Violence and gore",
    "language": "Profanity",
    "substances": "Alcohol, drugs and smoking",
    "frightening": "Frightening and intense scenes",
}

# IMDb's own severity words, lowercased to match the app's vocabulary.
SEVERITIES = {"none": "none-reported", "mild": "mild", "moderate": "moderate", "severe": "severe"}


class GuideUnavailable(Exception):
    """No guide could be fetched. The caller falls back to the estimate."""


async def _fetch(imdb_id: str) -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT) as http:
        response = await http.post(
            ENDPOINT,
            headers=HEADERS,
            json={"query": QUERY, "variables": {"id": imdb_id}},
        )
    if response.status_code != 200:
        raise GuideUnavailable(f"imdb returned {response.status_code}")
    payload = response.json()
    if payload.get("errors"):
        raise GuideUnavailable(str(payload["errors"][0].get("message"))[:200])
    return payload.get("data") or {}


def parse(data: dict[str, Any]) -> dict[str, Any]:
    """Turn the GraphQL shape into the app's advisory shape.

    Categories IMDb does not return are omitted rather than reported as
    empty: a missing category means nobody has written one up, which is not
    the same as nothing being there."""
    guide = ((data.get("title") or {}).get("parentsGuide") or {}).get("categories") or []
    categories = []
    for entry in guide:
        raw_id = str((entry.get("category") or {}).get("id") or "").lower()
        key = CATEGORY_KEYS.get(raw_id)
        if key is None:
            continue
        severity_text = str((entry.get("severity") or {}).get("text") or "").strip().lower()
        severity = SEVERITIES.get(severity_text, "none-reported")

        items: list[dict[str, Any]] = []
        node_edges = ((entry.get("guideItems") or {}).get("edges")) or []
        for edge in node_edges:
            node = edge.get("node") or {}
            text = str((node.get("text") or {}).get("plainText") or "").strip()
            if not text:
                continue
            items.append({"text": text[:1200], "spoiler": bool(node.get("isSpoiler"))})

        total = int(((entry.get("guideItems") or {}).get("total")) or len(items))
        categories.append(
            {
                "key": key,
                "label": LABELS[key],
                "severity": severity,
                # The first entry doubles as the one-line note the compact
                # view shows, so both views come from the same source.
                "note": str(items[0]["text"])[:400] if items and not items[0]["spoiler"] else "",
                "items": items,
                "total": total,
            }
        )
    if not categories:
        raise GuideUnavailable("imdb has no parents guide for this title")
    return {"categories": categories, "source": "imdb", "summary": ""}


async def for_title(db: AsyncSession, title: Title) -> dict[str, Any] | None:
    """The guide for one title, from cache when possible.

    Returns None when there is nothing to show, which the caller reads as
    "fall back to the estimate" rather than as an error."""
    if not title.imdb_id:
        return None
    key = f"imdbguide:{title.imdb_id}"
    cached = await cache.cache_get(db, key, TTL_HOURS)
    if cached is not None:
        # A cached miss is stored as an empty dict so a title IMDb has no
        # guide for is not re-fetched on every page view.
        return cached or None
    try:
        data = await _fetch(title.imdb_id)
        parsed = parse(data)
    except GuideUnavailable as exc:
        logger.info("no imdb guide for %s: %s", title.imdb_id, exc)
        await cache.cache_put(db, key, {})
        return None
    except (httpx.HTTPError, ValueError) as exc:
        # A transport failure is not cached: it says nothing about whether
        # a guide exists.
        logger.warning("imdb guide fetch failed for %s: %s", title.imdb_id, exc)
        return None
    await cache.cache_put(db, key, parsed)
    return parsed


async def titles_missing_guides(db: AsyncSession, limit: int = 20) -> list[Title]:
    """Titles with an IMDb id and no cached guide, newest first."""
    rows = (
        await db.execute(
            select(Title)
            .where(Title.imdb_id.is_not(None))
            .order_by(Title.popularity.desc().nulls_last())
            .limit(limit * 4)
        )
    ).scalars()
    out = []
    for title in rows:
        if await cache.cache_get(db, f"imdbguide:{title.imdb_id}", TTL_HOURS) is None:
            out.append(title)
        if len(out) >= limit:
            break
    return out
