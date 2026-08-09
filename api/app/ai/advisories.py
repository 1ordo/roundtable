"""Content advisories: what is actually in a title, category by category.

The official certification says a film is PG-13; it does not say why. This
fills that in the way a parents guide does, using the model over the plot,
genres, keywords and the certification itself.

Two rules make this safe to show:

  it never claims absence   the model may only report what it believes is
                            present. "No nudity" is not something it can
                            know from a synopsis, so it is never said.
  it is always labelled     every answer carries the fact that it is an
                            estimate from the description, not a report
                            from someone who watched the film.

Results are cached on the title so the same question is not paid for twice.
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import client
from app.models import Title, TitleAITag

logger = logging.getLogger("roundtable.advisories")

CACHE_SOURCE = "advisory"

CATEGORIES = [
    ("sex_nudity", "Sex and nudity"),
    ("violence", "Violence and gore"),
    ("language", "Profanity"),
    ("substances", "Alcohol, drugs and smoking"),
    ("frightening", "Frightening and intense scenes"),
]

SEVERITIES = ("none-reported", "mild", "moderate", "severe")

SYSTEM = """You write the content advisory section of a film guide, in the
style of a parents guide.

You are given a title's description, genres, keywords and its official age
ratings. Those ratings are real evidence: a board gave a film 15 or R for a
reason, and the genre says what kind of reason. Use them.

How to judge severity:
- Work from the rating and genre first. A PG-13 or 12A action film almost
  certainly carries moderate action violence; an R or 18 horror film carries
  strong violence and frightening scenes; a mature drama often carries
  language and substance use. Say so.
- Use the description for anything more specific it reveals.
- Severity is one of: none-reported, mild, moderate, severe.
- Use "none-reported" only when you genuinely have no evidence either way,
  and then leave the note empty.

What you must not do:
- Never state that something is absent. You have not watched this. Saying
  "no nudity" would be a claim you cannot support, so it is banned. Silence
  in a category means unknown, not clean.
- No plot spoilers beyond the description.
- No emojis. No em dashes.

Keep every note to one short sentence.

Return JSON only:
{"categories": [{"key": "sex_nudity", "severity": "...", "note": "..."},
                {"key": "violence", ...}, {"key": "language", ...},
                {"key": "substances", ...}, {"key": "frightening", ...}],
 "summary": "<one sentence on the overall tone and who it suits>"}"""


def _prompt(title: Title) -> str:
    bits = [f"Title: {title.name}" + (f" ({title.year})" if title.year else "")]
    bits.append("Series" if title.type == "tv" else "Film")
    if title.genres:
        bits.append("Genres: " + ", ".join(g.get("name", "") for g in title.genres))
    if title.certifications:
        shown = list(title.certifications.items())[:6]
        bits.append("Official ratings: " + ", ".join(f"{c}: {r}" for c, r in shown))
    if title.keywords:
        bits.append("Keywords: " + ", ".join(title.keywords[:30]))
    if title.overview:
        bits.append("Description: " + title.overview)
    return "\n".join(bits)


def _clean(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only the five known categories, and only valid severities."""
    by_key = {str(c.get("key")): c for c in payload.get("categories", []) if isinstance(c, dict)}
    categories = []
    for key, label in CATEGORIES:
        entry = by_key.get(key, {})
        severity = str(entry.get("severity", "none-reported")).strip().lower()
        if severity not in SEVERITIES:
            severity = "none-reported"
        note = str(entry.get("note") or "").strip()
        # A category with nothing to report carries no note, so the UI never
        # shows a sentence asserting the absence of something.
        if severity == "none-reported":
            note = ""
        categories.append({"key": key, "label": label, "severity": severity, "note": note[:400]})
    return {
        "categories": categories,
        "summary": str(payload.get("summary") or "").strip()[:400],
    }


async def cached(db: AsyncSession, title: Title) -> dict | None:
    row = (
        (
            await db.execute(
                select(TitleAITag).where(
                    TitleAITag.title_id == title.id, TitleAITag.source == CACHE_SOURCE
                )
            )
        )
        .scalars()
        .first()
    )
    if row is None or not row.detail:
        return None
    return row.detail


async def generate(db: AsyncSession, title: Title) -> dict:
    """Produce the advisory, reusing a stored answer when there is one."""
    existing = await cached(db, title)
    if existing is not None:
        return existing

    payload = await client.chat_json(db, SYSTEM, _prompt(title), max_tokens=1600)
    result = _clean(payload)

    db.add(
        TitleAITag(
            title_id=title.id,
            tag="content-advisory",
            source=CACHE_SOURCE,
            model="advisory-v1",
            detail=result,
        )
    )
    await db.flush()
    return result
