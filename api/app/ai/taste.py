"""Taste vectors and ranking: recency-weighted centroids over everything the
person tells us, explicitly (ratings, loved, like, dislike) and implicitly
(views, click-outs). Ranking adds diversity and exploration so a horror-heavy
history still surfaces things worth trying. Pure math; no LLM anywhere."""

import logging
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import ColumnElement, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.ai import client
from app.db import get_sessionmaker
from app.models import Interaction, Title, TitleEmbedding, User, UserTaste, WatchEvent

logger = logging.getLogger("roundtable.ai")

HALF_LIFE_DAYS = 180.0

# Signal weights. Watching outweighs clicking; explicit outweighs implicit.
# Writing about something is a stronger statement of interest than opening
# it or even clicking through to play it: it costs effort and it is on the
# record. Weighted just under an explicit like, which is still the clearest
# signal someone can give.
INTERACTION_WEIGHTS = {
    "like": 1.2,
    "dislike": -1.2,
    "comment": 1.0,
    # Deciding to save something is a deliberate statement of intent, worth
    # more than clicking through and less than saying you liked it.
    "save": 0.8,
    "click_out": 0.5,
    "view": 0.15,
}
VIEW_CAP_PER_TITLE = 3

# How much new signal is worth a rebuild, and how long a vector may stand
# regardless. Both keep the per-request cost flat as the audience grows.
# Rebuilt after this many new signals, or once it is this old, whichever
# comes first. Deliberately twitchy: the shelves are supposed to answer what
# you just did, and a vector that stands for a day makes the app feel like
# it is not listening. Rebuilding is a single query plus a weighted sum, so
# the cost of doing it often is small.
RECOMPUTE_AFTER_SIGNALS = 2
RECOMPUTE_AFTER = timedelta(hours=2)

# Ranking shape: how hard we push variety and how much we explore.
DIVERSITY_PENALTY = 0.35
LANGUAGE_BOOST = 0.06
# Following someone is an explicit statement of interest, so it outweighs a
# language preference but never overturns the similarity score itself.
FOLLOWED_BOOST = 0.12
EXPLORE_FRACTION = 0.15

# How adventurous the suggestions are, as (explore fraction, diversity
# penalty). Comfort stays close to what the person already likes; adventurous
# spends a third of every shelf on things outside their cluster.
DISCOVERY_MODES: dict[str, tuple[float, float]] = {
    "comfort": (0.05, 0.18),
    "balanced": (EXPLORE_FRACTION, DIVERSITY_PENALTY),
    "adventurous": (0.32, 0.55),
}

# Quality and popularity priors. Similarity says "this is your kind of
# thing"; these say "and it is actually worth your evening". Weights are
# deliberately small: taste leads, the priors break ties.
QUALITY_WEIGHT = 0.10
POPULARITY_WEIGHT = 0.05
RECENCY_WEIGHT = 0.04
# A rating means little until enough people have voted. This is the m in
# the standard Bayesian average, so a 9.5 from 40 votes does not outrank a
# 8.4 from 400,000.
VOTE_PRIOR = 2500
MEAN_RATING = 6.6


def quality_prior(title: Title) -> float:
    """Bayesian average of the rating, in 0 to 1.

    Shrinks thinly voted titles toward the global mean, which is what stops
    obscure 10-out-of-10s from dominating every shelf."""
    rating = title.tmdb_rating or title.imdb_rating
    if rating is None:
        return 0.5
    votes = title.tmdb_votes or 0
    adjusted = (votes * rating + VOTE_PRIOR * MEAN_RATING) / (votes + VOTE_PRIOR)
    return max(0.0, min(1.0, adjusted / 10.0))


def popularity_prior(title: Title) -> float:
    """Popularity on a log scale, so the top of the chart does not swamp
    everything below it."""
    popularity = title.popularity or 0.0
    if popularity <= 0:
        return 0.0
    return min(1.0, math.log10(1.0 + popularity) / 3.0)


def recency_prior(title: Title, now_year: int) -> float:
    """A gentle nudge toward things released in living memory, without
    burying the classics."""
    if not title.year:
        return 0.5
    age = max(0, now_year - title.year)
    return 0.5 ** (age / 25.0)


def _recency(when: datetime, now: datetime) -> float:
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    age_days = max(0.0, (now - when).total_seconds() / 86400)
    return 0.5 ** (age_days / HALF_LIFE_DAYS)


def event_weight(event: WatchEvent, now: datetime) -> float:
    if event.loved:
        base = 2.0
    elif event.rating_10 is not None:
        if event.rating_10 >= 7:
            base = 1.0
        elif event.rating_10 <= 4:
            base = -1.0
        else:
            base = 0.3
    else:
        base = 0.5
    return base * _recency(event.watched_at, now)


async def _signal_rows(db: AsyncSession, user: User, model: str) -> list[tuple[float, list]]:
    """(weight, embedding) pairs from watch events and interactions."""
    now = datetime.now(UTC)
    out: list[tuple[float, list]] = []

    events = (
        await db.execute(
            select(WatchEvent, TitleEmbedding.embedding)
            .join(
                TitleEmbedding,
                (TitleEmbedding.title_id == WatchEvent.title_id) & (TitleEmbedding.model == model),
            )
            .where(WatchEvent.user_id == user.id)
        )
    ).all()
    for event, embedding in events:
        out.append((event_weight(event, now), embedding))

    interactions = (
        await db.execute(
            select(Interaction, TitleEmbedding.embedding)
            .join(
                TitleEmbedding,
                (TitleEmbedding.title_id == Interaction.title_id) & (TitleEmbedding.model == model),
            )
            .where(Interaction.user_id == user.id)
        )
    ).all()
    view_counts: dict[uuid.UUID, int] = {}
    for interaction, embedding in interactions:
        weight = INTERACTION_WEIGHTS.get(interaction.kind, 0.0)
        if weight == 0.0:
            continue
        if interaction.kind == "view":
            seen = view_counts.get(interaction.title_id, 0)
            if seen >= VIEW_CAP_PER_TITLE:
                continue
            view_counts[interaction.title_id] = seen + 1
        out.append((weight * _recency(interaction.created_at, now), embedding))
    return out


async def _signal_count(db: AsyncSession, user: User, model: str) -> int:
    events = (
        await db.execute(
            select(WatchEvent.id)
            .join(
                TitleEmbedding,
                (TitleEmbedding.title_id == WatchEvent.title_id) & (TitleEmbedding.model == model),
            )
            .where(WatchEvent.user_id == user.id)
        )
    ).scalars()
    interactions = (
        await db.execute(
            select(Interaction.id)
            .join(
                TitleEmbedding,
                (TitleEmbedding.title_id == Interaction.title_id) & (TitleEmbedding.model == model),
            )
            .where(Interaction.user_id == user.id)
        )
    ).scalars()
    return len(list(events)) + len(list(interactions))


async def compute_taste(db: AsyncSession, user: User) -> np.ndarray | None:
    settings = await client.require_ai(db)
    model = settings.embed_model
    rows = await _signal_rows(db, user, model)
    if not rows:
        return None

    total = np.zeros(len(np.array(rows[0][1])), dtype=np.float64)
    weight_mass = 0.0
    for weight, embedding in rows:
        total += weight * np.array(embedding, dtype=np.float64)
        weight_mass += abs(weight)
    if weight_mass == 0:
        return None
    taste = total / weight_mass
    norm = np.linalg.norm(taste)
    if norm == 0:
        return None
    taste = taste / norm

    now = datetime.now(UTC)
    stmt = pg_insert(UserTaste).values(
        user_id=user.id,
        model=model,
        embedding=taste.tolist(),
        events_count=len(rows),
        computed_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[UserTaste.user_id],
        set_={
            "model": model,
            "embedding": taste.tolist(),
            "events_count": len(rows),
            "computed_at": now,
        },
    )
    # This cache write commits on its own connection. Holding the row lock
    # until the request's own commit lets two concurrent home loads that
    # each refresh both people's tastes deadlock on opposite orders.
    async with get_sessionmaker()() as cache_session:
        await cache_session.execute(stmt)
        await cache_session.commit()
    return taste


async def get_taste(db: AsyncSession, user: User) -> np.ndarray | None:
    """The cached taste vector, recomputed only when it would move.

    Rebuilding reads every signal and its embedding, so doing it on each
    request would put that cost on every page view. One more view does not
    change a centroid built from hundreds of signals, so the rebuild waits
    until enough has accumulated, or until the vector is a day old. Anything
    that should show up at once, a like or a rating, goes through
    invalidate_taste and skips the wait."""
    settings = await client.require_ai(db)
    cached = (
        await db.execute(select(UserTaste).where(UserTaste.user_id == user.id))
    ).scalar_one_or_none()
    if cached is None or cached.model != settings.embed_model:
        return await compute_taste(db, user)

    count = await _signal_count(db, user, settings.embed_model)
    drift = abs(count - (cached.events_count or 0))
    computed = cached.computed_at
    if computed is not None and computed.tzinfo is None:
        computed = computed.replace(tzinfo=UTC)
    aged = computed is None or datetime.now(UTC) - computed > RECOMPUTE_AFTER

    if drift >= RECOMPUTE_AFTER_SIGNALS or aged:
        return await compute_taste(db, user)
    return np.array(cached.embedding)


async def invalidate_taste(db: AsyncSession, user: User) -> None:
    """Force the next read to rebuild.

    Used after a deliberate act, a like, a dislike or a rating, where the
    person should see the effect immediately rather than after a few more
    signals accumulate."""
    cached = (
        await db.execute(select(UserTaste).where(UserTaste.user_id == user.id))
    ).scalar_one_or_none()
    if cached is not None:
        cached.events_count = -1
        await db.flush()


def blend_tastes(tastes: list[np.ndarray], weights: list[float] | None = None) -> np.ndarray:
    """Movie night: weighted average of everyone in the room."""
    if weights is None:
        weights = [1.0] * len(tastes)
    total = np.zeros_like(tastes[0])
    for taste, weight in zip(tastes, weights, strict=True):
        total += weight * taste
    norm = np.linalg.norm(total)
    return total / norm if norm else total


@dataclass(frozen=True)
class ServiceFilter:
    """Which services to keep a suggestion for, and where they count.

    Two lists because they are answered by different evidence. `providers`
    are services the source lists in this person's countries, so a missing
    row there is a real absence and the country condition is meaningful.
    `anywhere` are services it does not list in their countries at all: no
    country condition can be applied to a service the data has never heard
    of in that region, and applying one anyway removed every Disney Plus
    title from anybody watching from Egypt.
    """

    providers: list[int]
    countries: list[str]
    anywhere: list[int]

    @property
    def matches_anything(self) -> bool:
        return bool((self.providers and self.countries) or self.anywhere)


async def rank_titles_by_vector(
    db: AsyncSession,
    vector: np.ndarray,
    limit: int = 20,
    exclude_title_ids: set[uuid.UUID] | None = None,
    media_type: str | None = None,
    on_services: ServiceFilter | None = None,
) -> list[tuple[Title, float]]:
    settings = await client.require_ai(db)
    # How much of the HNSW graph to walk. The default of 40 gives poor
    # recall once a shelf asks for a pool of a hundred or more, and a shelf
    # that quietly returns near-misses is worse than a slow one. Set per
    # session because it is a planner hint, not a schema property.
    await db.execute(text("SET LOCAL hnsw.ef_search = 200"))
    query = (
        select(Title, TitleEmbedding.embedding.cosine_distance(vector.tolist()).label("dist"))
        .join(TitleEmbedding, TitleEmbedding.title_id == Title.id)
        # The full provider payload averages thirteen kilobytes a title, and
        # ranking never looks at it. Left in, a few hundred candidates is
        # megabytes off the wire and a JSON parse for each one, all thrown
        # away. Anything that does need it asks Postgres directly.
        .options(defer(Title.raw_tmdb))
        .where(TitleEmbedding.model == settings.embed_model)
    )
    if media_type in ("movie", "tv"):
        query = query.where(Title.type == media_type)
    if on_services is not None and on_services.matches_anything:
        # Kept in SQL rather than filtered afterwards. Done in Python it
        # would mean fetching a pool several times larger and throwing most
        # of it away, and the shelf would still run short for anyone whose
        # taste sits outside what their own services carry.
        from sqlalchemy import or_

        from app.models import Availability

        wanted: list[ColumnElement[bool]] = []
        if on_services.providers and on_services.countries:
            wanted.append(
                (Availability.provider_id.in_(on_services.providers))
                & (Availability.country.in_(on_services.countries))
            )
        if on_services.anywhere:
            # No country condition, because there is no country data to
            # condition on. See app.catalog.coverage.
            wanted.append(Availability.provider_id.in_(on_services.anywhere))
        query = query.where(
            select(Availability.title_id)
            .where(Availability.title_id == Title.id, or_(*wanted))
            .exists()
        )
    query = query.order_by("dist").limit(limit + len(exclude_title_ids or ()))
    rows = (await db.execute(query)).all()
    out: list[tuple[Title, float]] = []
    for title, dist in rows:
        if exclude_title_ids and title.id in exclude_title_ids:
            continue
        out.append((title, 1.0 - float(dist)))
        if len(out) >= limit:
            break
    return out


# Whether anyone followed appears in the top billing or directed it. Only the
# top of the cast counts: a followed actor in the twentieth credit is not why
# anyone would want to watch something.
#
# Asked of Postgres rather than in Python because the answer lives inside
# raw_tmdb, and shipping that column back for a whole candidate pool costs far
# more than the small boost it feeds. The typeof guards matter: a title
# ingested before credits were fetched has no array there, and
# jsonb_array_elements raises on anything that is not one.
_FOLLOWED_SQL = text("""
    SELECT t.id FROM titles t
    WHERE t.id = ANY(:ids)
      AND jsonb_typeof(t.raw_tmdb -> 'credits') = 'object'
      AND (
        EXISTS (
          SELECT 1
          FROM jsonb_array_elements(t.raw_tmdb -> 'credits' -> 'cast')
               WITH ORDINALITY AS c(member, position)
          WHERE jsonb_typeof(t.raw_tmdb -> 'credits' -> 'cast') = 'array'
            AND c.position <= 10
            AND (c.member ->> 'id') ~ '^[0-9]+$'
            AND (c.member ->> 'id')::int = ANY(:people)
        )
        OR EXISTS (
          SELECT 1
          FROM jsonb_array_elements(t.raw_tmdb -> 'credits' -> 'crew') AS c(member)
          WHERE jsonb_typeof(t.raw_tmdb -> 'credits' -> 'crew') = 'array'
            AND c.member ->> 'job' = 'Director'
            AND (c.member ->> 'id') ~ '^[0-9]+$'
            AND (c.member ->> 'id')::int = ANY(:people)
        )
      )
""")


async def followed_title_ids(
    db: AsyncSession, title_ids: list[uuid.UUID], people: set[int]
) -> set[uuid.UUID]:
    """Which of these titles star or were directed by someone followed."""
    if not title_ids or not people:
        return set()
    rows = await db.execute(_FOLLOWED_SQL, {"ids": list(title_ids), "people": list(people)})
    return set(rows.scalars())


def _genre_ids(title: Title) -> set[int]:
    return {g.get("id") for g in (title.genres or []) if g.get("id") is not None}


@dataclass
class ScoredPool:
    """Candidates near a taste vector, each scored but not yet arranged."""

    items: list[tuple[Title, float]]
    # Which of them star or were directed by someone this person follows.
    # Carried alongside because it costs a query to work out and more than
    # one shelf wants to know.
    starring: set[uuid.UUID]

    def __bool__(self) -> bool:
        return bool(self.items)


async def score_pool(
    db: AsyncSession,
    vector: np.ndarray,
    size: int,
    exclude_title_ids: set[uuid.UUID] | None = None,
    languages: list[str] | None = None,
    followed_people: set[int] | None = None,
    media_type: str | None = None,
    on_services: ServiceFilter | None = None,
) -> ScoredPool:
    """Score a pool of candidates, once.

    Split out from the ranking because one pool feeds many shelves. Asking
    pgvector once for several hundred candidates and slicing that in Python
    is a fraction of the cost of a query per shelf, and it keeps the shelves
    honest with each other: the same title cannot be a strong fit on one and
    missing from another."""
    pool = await rank_titles_by_vector(db, vector, size, exclude_title_ids, media_type, on_services)
    if not pool:
        return ScoredPool(items=[], starring=set())

    starring = await followed_title_ids(db, [t.id for t, _ in pool], followed_people or set())
    now_year = datetime.now(UTC).year
    # Scored once, up front: none of these priors depend on what has already
    # been picked, so recomputing them inside the greedy pass would be work
    # thrown away on every iteration.
    items = [
        (
            title,
            sim
            + QUALITY_WEIGHT * quality_prior(title)
            + POPULARITY_WEIGHT * popularity_prior(title)
            + RECENCY_WEIGHT * recency_prior(title, now_year)
            + (LANGUAGE_BOOST if languages and title.original_language in languages else 0.0)
            + (FOLLOWED_BOOST if title.id in starring else 0.0),
        )
        for title, sim in pool
    ]
    return ScoredPool(items=items, starring=starring)


def arrange(
    scored: list[tuple[Title, float]],
    limit: int,
    discovery: str = "balanced",
) -> list[tuple[Title, float]]:
    """Greedy reranking of an already scored pool.

    Each pick is penalized by its genre overlap with what is already picked,
    and the last slots are exploration: well liked titles from outside the
    taste cluster, so the algorithm keeps trying new things."""
    if not scored:
        return []

    explore_fraction, diversity_penalty = DISCOVERY_MODES.get(
        discovery, DISCOVERY_MODES["balanced"]
    )
    explore_slots = max(1, int(limit * explore_fraction)) if len(scored) > limit else 0
    core_slots = limit - explore_slots

    remaining = list(scored)
    genres = [_genre_ids(title) for title, _ in remaining]
    # The running overlap between each candidate and the best matching thing
    # already picked. Folding each new pick into this costs one pass over
    # what is left, where rescanning the whole selection each time made a
    # long shelf quadratic in its own length.
    penalty = [0.0] * len(remaining)

    selected: list[tuple[Title, float]] = []
    while remaining and len(selected) < core_slots:
        best_index = 0
        best_score = -1e9
        for index, (_, prior_score) in enumerate(remaining):
            score = prior_score - diversity_penalty * penalty[index]
            if score > best_score:
                best_score = score
                best_index = index

        picked_genres = genres.pop(best_index)
        penalty.pop(best_index)
        selected.append(remaining.pop(best_index))

        if picked_genres:
            for index, candidate_genres in enumerate(genres):
                if not candidate_genres:
                    continue
                overlap = len(candidate_genres & picked_genres) / len(
                    candidate_genres | picked_genres
                )
                if overlap > penalty[index]:
                    penalty[index] = overlap

    if explore_slots:
        # The bottom similarity half of the pool, most popular first: things
        # the person would probably not have been shown otherwise, but that
        # are well liked enough to be a fair bet.
        tail = sorted(remaining, key=lambda pair: pair[1])[: max(explore_slots * 4, 8)]
        tail.sort(key=lambda pair: -(quality_prior(pair[0]) + popularity_prior(pair[0])))
        selected.extend(tail[:explore_slots])

    return selected


async def diversified_ranking(
    db: AsyncSession,
    vector: np.ndarray,
    limit: int = 20,
    exclude_title_ids: set[uuid.UUID] | None = None,
    languages: list[str] | None = None,
    discovery: str = "balanced",
    followed_people: set[int] | None = None,
    media_type: str | None = None,
    on_services: ServiceFilter | None = None,
) -> list[tuple[Title, float]]:
    """The anti-bubble ranking: score a pool, then arrange it."""
    pool = await score_pool(
        db,
        vector,
        limit * 3,
        exclude_title_ids,
        languages=languages,
        followed_people=followed_people,
        media_type=media_type,
        on_services=on_services,
    )
    return arrange(pool.items, limit, discovery)


async def match_scores(
    db: AsyncSession, user: User, title_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """How well each title fits this person, as a 0-100 number.

    Everything they do feeds this: watches, ratings, loves, likes, dislikes,
    click-outs and views all shape the taste vector this is measured against.
    Returns an empty map when there is not enough signal yet, so the UI can
    simply omit the badge."""
    if not title_ids:
        return {}
    try:
        settings = await client.require_ai(db)
        vector = await get_taste(db, user)
    except client.AIDisabled:
        return {}
    if vector is None:
        return {}

    rows = (
        await db.execute(
            select(
                TitleEmbedding.title_id,
                TitleEmbedding.embedding.cosine_distance(vector.tolist()).label("dist"),
            ).where(
                TitleEmbedding.title_id.in_(title_ids),
                TitleEmbedding.model == settings.embed_model,
            )
        )
    ).all()

    scores: dict[uuid.UUID, int] = {}
    for title_id, distance in rows:
        similarity = 1.0 - float(distance)
        # Cosine similarity here lives roughly in 0 to 0.5; stretch that into
        # a percentage that reads naturally without ever claiming 100.
        percent = int(round(min(0.55, max(0.0, similarity)) / 0.55 * 96))
        scores[title_id] = percent
    return scores


async def watched_title_ids(db: AsyncSession, user: User) -> set[uuid.UUID]:
    rows = (
        await db.execute(select(WatchEvent.title_id).where(WatchEvent.user_id == user.id))
    ).scalars()
    watched = set(rows)
    disliked = (
        await db.execute(
            select(Interaction.title_id).where(
                Interaction.user_id == user.id, Interaction.kind == "dislike"
            )
        )
    ).scalars()
    return watched | set(disliked)
