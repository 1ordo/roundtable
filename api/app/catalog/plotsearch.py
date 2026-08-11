"""Finding a title from a description of what happens in it.

The vector index answers "more like this one". It cannot answer "the one
where a guy relives the same day", because the default encoder is lexical:
it compares the literal strings two texts share. Measured on a real 21,000
title catalog, that question put Groundhog Day at rank 13,614 of 21,018.

What does work is already on disk. TMDB keywords are the concept vocabulary
people actually use, and they are indexed here as the highest-weighted part
of titles.search_doc. Groundhog Day carries "time loop" and "deja vu";
Inception carries "dream world" and "subconscious". Inception's overview
never contains the word "dream", so no amount of searching the plot prose
finds it, and searching the keywords finds it first.

Two rules learned by measuring:

  Relevance leads, priors break ties. Ranking a broad match by quality and
  popularity alone returns whatever is most famous: asked about time loops
  it answered Parasite. The same rule is already written down in
  app/ai/taste.py, and it holds here.

  The no-model fallback ANDs its terms rather than ORing them. "the movie
  where a guy shrinks his kids" with AND returns Honey, I Shrunk the Kids
  first; with OR it returns House Party.
"""

import logging
import re

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Title

logger = logging.getLogger("roundtable.plotsearch")

# Words that carry no signal in "the one where they go into dreams". Left in,
# they dominate a short query: the framing alone scored a disaster film above
# Inception.
_STOP = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "called",
    "can",
    "did",
    "do",
    "film",
    "films",
    "for",
    "from",
    "guy",
    "had",
    "has",
    "have",
    "he",
    "her",
    "him",
    "his",
    "i",
    "in",
    "into",
    "is",
    "it",
    "its",
    "know",
    "like",
    "man",
    "me",
    "movie",
    "movies",
    "name",
    "of",
    "on",
    "one",
    "or",
    "over",
    "person",
    "remember",
    "same",
    "series",
    "she",
    "show",
    "shows",
    "some",
    "something",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "they",
    "thing",
    "this",
    "to",
    "up",
    "was",
    "watch",
    "watched",
    "we",
    "what",
    "when",
    "where",
    "which",
    "who",
    "with",
    "woman",
    "you",
}

_WORD = re.compile(r"[a-z0-9']+")

CONCEPT_SYSTEM = """You turn a vague description of a film or series into the
words a film database would tag it with.

Reply as JSON: {"concepts": ["time loop", "deja vu"], "titles": []}

concepts: two to six short tag-like phrases, lowercase, the vocabulary a
catalogue uses rather than the words the person used. "relives the same day"
becomes "time loop". "goes into dreams" becomes "dream world". Do not include
genres unless the person named one.

titles: any actual title the person named, or [] if none. Never guess a title
you are not certain they said."""


def fallback_terms(question: str) -> list[str]:
    """Concept terms without a model: whatever survives stripping framing."""
    words = [w for w in _WORD.findall(question.lower()) if w not in _STOP and len(w) > 2]
    seen: list[str] = []
    for word in words:
        if word not in seen:
            seen.append(word)
    return seen[:6]


def _tsquery(concepts: list[str], joiner: str) -> str:
    """Concepts to a tsquery string. Multi-word concepts become phrases, so
    "time loop" matches the phrase rather than the two words anywhere."""
    parts = []
    for concept in concepts:
        words = _WORD.findall(concept.lower())
        words = [w for w in words if w not in _STOP or len(words) == 1]
        if not words:
            continue
        parts.append(" <-> ".join(words) if len(words) > 1 else words[0])
    return f" {joiner} ".join(f"({p})" for p in parts)


async def search(
    db: AsyncSession,
    concepts: list[str],
    limit: int = 24,
    require_all: bool = False,
) -> list[Title]:
    """Titles matching a set of concepts, best match first.

    require_all ANDs the terms, which is what the no-model path wants: the
    words came straight from the person, so all of them should appear.
    Concepts from a model are already abstracted, so those are ORed.
    """
    if not concepts:
        return []
    query = _tsquery(concepts, "&" if require_all else "|")
    if not query:
        return []

    # ts_rank_cd first, always. The priors are a tiebreak within equally
    # relevant rows and must never outrank the match itself.
    stmt = text(
        """
        SELECT id
        FROM titles
        WHERE search_doc @@ to_tsquery('english', :q)
        ORDER BY
            ts_rank_cd('{0.1,1.0,0.5,0.3}', search_doc, to_tsquery('english', :q)) DESC,
            (coalesce(tmdb_votes,0)::float / (coalesce(tmdb_votes,0) + 2500))
                * coalesce(tmdb_rating, 6.6) DESC,
            coalesce(popularity, 0) DESC
        LIMIT :lim
        """
    ).bindparams(bindparam("q", query), bindparam("lim", limit))

    try:
        ids = list((await db.execute(stmt)).scalars().all())
    except Exception:
        # A malformed tsquery is a bad question, not a broken instance.
        logger.info("plot search could not parse %r", query)
        return []
    if not ids:
        return []

    from sqlalchemy import select

    rows = (await db.execute(select(Title).where(Title.id.in_(ids)))).scalars().all()
    order = {tid: i for i, tid in enumerate(ids)}
    return sorted(rows, key=lambda t: order.get(t.id, 999))


async def concepts_for(db: AsyncSession, question: str) -> list[str]:
    """Ask the model for catalogue vocabulary, or fall back to the question.

    The fallback is not a stub. Measured: "the movie where a guy shrinks his
    kids" returns Honey, I Shrunk the Kids at rank one with no model at all.
    It is weaker when the person's words and the catalogue's words differ,
    which is exactly what the model is for.
    """
    from app.ai import client

    try:
        payload = await client.chat_json(db, CONCEPT_SYSTEM, question, max_tokens=200)
        concepts = [str(c).strip() for c in (payload.get("concepts") or []) if str(c).strip()]
        if concepts:
            return concepts[:6]
    except Exception:
        logger.info("no model for concept extraction; using the question as written")
    return fallback_terms(question)


async def find(db: AsyncSession, question: str, limit: int = 24) -> list[Title]:
    """The whole path: question in, plausible titles out.

    Tries model concepts first, then the person's own words ANDed together.
    Both legs are the same index; only the terms differ.
    """
    concepts = await concepts_for(db, question)
    found = await search(db, concepts, limit=limit)
    if found:
        return found
    words = fallback_terms(question)
    found = await search(db, words, limit=limit, require_all=True)
    if found:
        return found
    # Last resort: drop the rarest requirement rather than answer nothing.
    return await search(db, words[:2], limit=limit, require_all=True) if len(words) > 2 else []
