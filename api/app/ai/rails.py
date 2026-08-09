"""Personalized shelves: many angles on one taste vector.

A single "Picked for you" row proves the algorithm runs. It does not make
the app useful, because it answers one question — what is closest to the
centroid of everything you have ever watched — and that question has a
short answer. Everything past the top twenty is a worse version of the top
twenty.

So the pool is fetched wide, once, and then read through several lenses.
Your genres, but only the ones you watch more than the catalog average.
Things nobody would otherwise put in front of you. What came out this year.
What came out before you were born. Each lens is a different question with a
different answer, and together they fill a page the way a streaming service
does, without ever leaving the taste vector behind.

None of this calls a model. It is the same cosine similarity and the same
priors as the main shelf, partitioned.
"""

import logging
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import client as ai_client
from app.ai import taste as taste_module
from app.countries import for_user as countries_for
from app.models import FollowedPerson, Interaction, Title, User, WatchEvent

logger = logging.getLogger("watchpile.ai")

# How many candidates to score in one go. Wide enough that a genre shelf and
# a decade shelf can be cut from the same cloth without either running thin,
# and small enough to stay one fast query: the vector column is the only
# heavy part and raw_tmdb is left behind.
POOL = 500

# The headline shelf, and everything under it. The main row is deliberately
# long: it is the one people scroll, and stopping at twenty was the single
# most common complaint.
MAIN_SHELF = 40
SHELF = 24
# Below this a shelf reads as an apology rather than a suggestion, so it is
# dropped instead.
MIN_SHELF = 8

# At most this many genre shelves, however many genres clear the bar.
GENRE_SHELVES = 6
# And how many "because you watched X" rows. These are the most reactive rows
# on the page; more than a few and the page is about your history instead.
ANCHOR_SHELVES = 2
# Shelves named after where the viewing comes from: K-drama, anime, Turkish
# drama. Capped low because two or three is a section and six is a filter.
LANGUAGE_SHELVES = 3
# A language has to be further out of proportion than a genre to earn a row,
# because there are fewer of them and the catalog leans hard towards English.
MIN_LANGUAGE_LIFT = 1.4
MIN_LANGUAGE_WEIGHT = 2.0
# How much more often than the catalog average you must watch a genre before
# it earns a row. At 1.0 everyone gets a Drama shelf, which tells them
# nothing about themselves.
MIN_LIFT = 1.25
# And how much of that genre you must actually have watched, so one horror
# film in a history of forty does not become a horror shelf.
MIN_GENRE_WEIGHT = 2.0

# A gem is well liked but not widely seen. Both halves matter: without the
# quality floor this is a shelf of things that flopped for a reason.
GEM_MAX_POPULARITY = 0.42
GEM_MIN_QUALITY = 0.63

# What counts as new, and what counts as old enough to be worth rediscovering.
FRESH_YEARS = 2
VINTAGE_YEARS = 25
# A film you can start at ten and still get to bed.
SHORT_RUNTIME = 105
# High enough that the row means something. The Bayesian prior is already
# shrinking thin vote counts towards the mean, so this is a real bar.
ACCLAIMED_MIN_QUALITY = 0.74

# How far back to read watch history when working out genre affinity, and how
# quickly older viewing stops counting.
AFFINITY_HALF_LIFE_DAYS = 240.0

# The catalog's own genre mix barely moves between deploys, and every request
# would otherwise pay for the same scan. Keyed by media type, since films and
# series have quite different mixes.
_BASE_RATE_TTL = timedelta(hours=6)
_base_rates: dict[str, tuple[datetime, dict[int, float]]] = {}


# What people actually call these, rather than what the language code says.
# "Korean series" is not a phrase anyone uses or searches for.
LANGUAGE_NAMES: dict[str, str] = {
    "ar": "Arabic",
    "de": "German",
    "es": "Spanish-language",
    "fa": "Iranian",
    "fr": "French",
    "hi": "Indian",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "pt": "Brazilian and Portuguese",
    "ru": "Russian",
    "sv": "Swedish",
    "th": "Thai",
    "tr": "Turkish",
    "zh": "Chinese",
    "cn": "Hong Kong and Chinese",
    "da": "Danish",
    "nl": "Dutch",
    "no": "Norwegian",
    "pl": "Polish",
}

ANIMATION_GENRE = 16


@dataclass
class Shelf:
    """One row on the page."""

    key: str
    title: str
    titles: list[Title] = field(default_factory=list)


# Things there is no way to watch tonight, which is what a suggestion is for.
#
# Two cases. Something with a date in the future has not come out. Something
# that came out in the last year and is listed by nobody is in cinemas: the
# absence of a listing is the signal, because a film on release simply has no
# streaming entry yet. That second rule is deliberately not extended to older
# titles, where an empty listing is far more likely to be a gap in the crawl
# than a statement about where the film is playing.
#
# Availability is checked anywhere rather than in the viewer's own country on
# purpose. Coverage by country is uneven — a catalog can be 87 percent listed
# in the US and 42 percent in Egypt — so requiring a local listing would throw
# away most of the shelf to answer a question the data cannot actually answer.
# Anywhere-listed is the claim the data supports: this exists to be streamed,
# rather than this is only in cinemas.
_UNWATCHABLE = text("""
    SELECT t.id FROM titles t
    WHERE COALESCE(
            NULLIF(t.raw_tmdb ->> 'release_date', ''),
            NULLIF(t.raw_tmdb ->> 'first_air_date', ''),
            '0000-00-00'
          ) > :today
       OR (
            t.type = 'movie'
            AND COALESCE(NULLIF(t.raw_tmdb ->> 'release_date', ''), '0000-00-00') > :a_year_ago
            AND NOT EXISTS (SELECT 1 FROM availability a WHERE a.title_id = t.id)
          )
""")


async def unwatchable_title_ids(db: AsyncSession) -> set[uuid.UUID]:
    """Everything that cannot be started at home right now."""
    today = datetime.now(UTC).date()
    rows = await db.execute(
        _UNWATCHABLE,
        {
            "today": today.isoformat(),
            "a_year_ago": (today - timedelta(days=365)).isoformat(),
        },
    )
    return set(rows.scalars())


# One reference to the parameter, not two: `:media_type::text IS NULL OR ...`
# reads to SQLAlchemy's text() parser as a bind name followed by a stray
# colon, and ships malformed SQL. COALESCE says the same thing once.
_GENRE_COUNTS = text("""
    SELECT (g.value ->> 'id')::int AS genre_id, count(*) AS n
    FROM titles t, jsonb_array_elements(t.genres) AS g(value)
    WHERE jsonb_typeof(t.genres) = 'array'
      AND (g.value ->> 'id') ~ '^[0-9]+$'
      AND t.type = COALESCE(CAST(:media_type AS text), t.type)
    GROUP BY 1
""")


async def _catalog_base_rates(db: AsyncSession, media_type: str | None) -> dict[int, float]:
    """What share of the catalog each genre is.

    The denominator for affinity. Without it the top genre is whichever one
    the catalog has most of, for everybody, forever."""
    cache_key = media_type or "all"
    now = datetime.now(UTC)
    cached = _base_rates.get(cache_key)
    if cached is not None and now - cached[0] < _BASE_RATE_TTL:
        return cached[1]

    rows = (await db.execute(_GENRE_COUNTS, {"media_type": media_type})).all()
    total = sum(int(n) for _, n in rows) or 1
    rates = {int(genre_id): int(n) / total for genre_id, n in rows}

    _base_rates[cache_key] = (now, rates)
    return rates


async def affinity_genres(
    db: AsyncSession, user: User, media_type: str | None = None
) -> list[tuple[int, str]]:
    """The genres this person watches more than the catalog average.

    Ordered by lift rather than by count, so the answer is what is
    distinctive about them and not what is common about the catalog."""
    now = datetime.now(UTC)

    def recency(when: datetime) -> float:
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        days = max(0.0, (now - when).total_seconds() / 86400)
        return 0.5 ** (days / AFFINITY_HALF_LIFE_DAYS)

    watched = (
        select(Title.genres, WatchEvent.watched_at)
        .join(WatchEvent, WatchEvent.title_id == Title.id)
        .where(WatchEvent.user_id == user.id)
    )
    liked = (
        select(Title.genres, Interaction.created_at)
        .join(Interaction, Interaction.title_id == Title.id)
        .where(Interaction.user_id == user.id, Interaction.kind.in_(("like", "comment")))
    )
    if media_type in ("movie", "tv"):
        watched = watched.where(Title.type == media_type)
        liked = liked.where(Title.type == media_type)

    weights: dict[int, float] = {}
    names: dict[int, str] = {}
    total = 0.0
    for query in (watched, liked):
        for genres, when in (await db.execute(query)).all():
            weight = recency(when)
            for entry in genres or []:
                genre_id = entry.get("id")
                if genre_id is None:
                    continue
                weights[genre_id] = weights.get(genre_id, 0.0) + weight
                names.setdefault(genre_id, entry.get("name") or "")
                total += weight

    if total <= 0:
        return []

    base = await _catalog_base_rates(db, media_type)
    ranked: list[tuple[float, int]] = []
    for genre_id, weight in weights.items():
        if weight < MIN_GENRE_WEIGHT:
            continue
        share = weight / total
        # An unknown genre is treated as rare rather than as impossible, so a
        # newly added one can still surface instead of dividing by zero.
        lift = share / max(base.get(genre_id, 0.005), 0.005)
        if lift < MIN_LIFT:
            continue
        ranked.append((lift, genre_id))

    ranked.sort(reverse=True)
    return [(genre_id, names.get(genre_id) or f"Genre {genre_id}") for _, genre_id in ranked]


def _take(
    pool: list[tuple[Title, float]],
    predicate,
    used: set[uuid.UUID],
    limit: int = SHELF,
) -> list[Title]:
    """The best unused candidates matching a lens.

    Already-shown titles are skipped rather than repeated: a page where the
    same six films appear on four shelves is worse than a page with fewer
    shelves, because it makes the whole thing look like one shelf wearing
    hats."""
    out: list[Title] = []
    for title, _ in pool:
        if title.id in used or not title.poster_path:
            continue
        if not predicate(title):
            continue
        out.append(title)
        if len(out) >= limit:
            break
    return out


def _add(
    shelves: list[Shelf],
    used: set[uuid.UUID],
    key: str,
    name: str,
    titles: list[Title],
    minimum: int = MIN_SHELF,
):
    if len(titles) < minimum:
        return
    shelves.append(Shelf(key=key, title=name, titles=titles))
    used.update(t.id for t in titles)


async def _anchors(db: AsyncSession, user: User, how_many: int) -> list[tuple[Title, str]]:
    """The most recent things this person committed to, newest first.

    A bare view is deliberately not a commitment. Opening a title and leaving
    without saving, rating or reacting is closer to "no" than to "yes", and
    building a whole shelf on it makes the app feel like it is watching
    rather than listening.

    A watch that was rated badly is not one either: a film you gave four out
    of ten is a reason to show you less like it, not more."""
    from app.models import List, ListItem

    rows: list[tuple[datetime, uuid.UUID, str]] = []

    liked = await db.execute(
        select(Interaction.title_id, Interaction.created_at, Interaction.kind)
        .where(Interaction.user_id == user.id, Interaction.kind.in_(("like", "click_out")))
        .order_by(Interaction.created_at.desc())
        .limit(how_many * 4)
    )
    rows += [(when, title_id, "liked") for title_id, when, _ in liked.all()]

    watched = await db.execute(
        select(WatchEvent.title_id, WatchEvent.watched_at, WatchEvent.loved, WatchEvent.rating_10)
        .where(WatchEvent.user_id == user.id)
        .order_by(WatchEvent.watched_at.desc())
        .limit(how_many * 4)
    )
    rows += [
        (when, title_id, "watched")
        for title_id, when, loved, rating in watched.all()
        if loved or rating is None or rating >= 6
    ]

    saved = await db.execute(
        select(ListItem.title_id, ListItem.added_at)
        .join(List, List.id == ListItem.list_id)
        .where(List.user_id == user.id, List.kind != "cinema")
        .order_by(ListItem.added_at.desc())
        .limit(how_many * 4)
    )
    rows += [(when, title_id, "saved") for title_id, when in saved.all()]

    def when_of(row: tuple[datetime, uuid.UUID, str]) -> datetime:
        # The three sources disagree about tzinfo, and comparing an aware
        # datetime with a naive one raises rather than sorting wrong.
        return row[0].replace(tzinfo=UTC) if row[0].tzinfo is None else row[0]

    rows.sort(key=when_of, reverse=True)

    out: list[tuple[Title, str]] = []
    seen: set[uuid.UUID] = set()
    for _, title_id, verb in rows:
        if title_id in seen or len(out) >= how_many:
            continue
        seen.add(title_id)
        title = (await db.execute(select(Title).where(Title.id == title_id))).scalar_one_or_none()
        if title is not None:
            out.append((title, verb))
    return out


async def _anchor_shelves(
    db: AsyncSession,
    user: User,
    exclude: set[uuid.UUID],
    media_type: str | None,
    how_many: int = ANCHOR_SHELVES,
    depth: int = 1,
) -> list[Shelf]:
    """Because you watched X, for the last few things they committed to.

    These get their own pgvector query per anchor rather than reusing the
    taste pool, because that is the whole point of them: they answer what is
    like this one film, not what is like everything at once. It also means
    the home page reacts to today's clicks without rearranging itself, since
    only these rows change name and contents."""
    from app.models import TitleEmbedding

    try:
        settings = await ai_client.require_ai(db)
    except (ai_client.AIDisabled, ai_client.AIError):
        return []

    import numpy as np

    shelves: list[Shelf] = []
    # Distinct from each other, though not from the rest of the page: two
    # anchors from the same evening are often similar enough that without
    # this the second row is the first one again.
    between: set[uuid.UUID] = set()
    for anchor, verb in await _anchors(db, user, how_many * 2):
        if len(shelves) >= how_many:
            break
        embedding = (
            await db.execute(
                select(TitleEmbedding).where(
                    TitleEmbedding.title_id == anchor.id,
                    TitleEmbedding.model == settings.embed_model,
                )
            )
        ).scalar_one_or_none()
        if embedding is None:
            continue

        ranked = await taste_module.diversified_ranking(
            db,
            np.array(embedding.embedding),
            SHELF * depth,
            exclude | between | {anchor.id},
            media_type=media_type,
        )
        titles = [t for t, _ in ranked if t.poster_path]
        if not titles:
            continue
        shelves.append(
            Shelf(
                key=f"because-{anchor.type}-{anchor.tmdb_id}",
                title=f"Because you {verb} {anchor.name}",
                titles=titles,
            )
        )
        between.update(t.id for t in titles)
    return shelves


def _language_shelf_title(code: str, titles: list[Title]) -> str:
    """Name the shelf after what is in it.

    A Korean shelf that turns out to be all series is a K-drama shelf, and a
    Japanese one that is mostly animation is an anime shelf. Deciding this
    from the contents rather than from the request means the same lens gets
    the right name on the home page, the films page and the series page
    without three sets of rules."""
    series = sum(1 for t in titles if t.type == "tv")
    mostly_series = series >= len(titles) * 0.7
    animated = sum(
        1 for t in titles if any(g.get("id") == ANIMATION_GENRE for g in (t.genres or []))
    )
    mostly_animated = animated >= len(titles) * 0.6

    if code == "ko" and mostly_series:
        return "K-drama for you"
    if code == "ja" and mostly_animated:
        return "Anime for you"
    if code == "tr" and mostly_series:
        return "Turkish drama for you"
    if code == "zh" and mostly_series:
        return "C-drama for you"

    name = LANGUAGE_NAMES.get(code)
    if not name:
        return "More like this for you"
    kind = "series" if mostly_series else "films" if all(t.type == "movie" for t in titles) else ""
    return f"{name} {kind} for you".replace("  ", " ")


_LANGUAGE_COUNTS = text("""
    SELECT t.original_language AS code, count(*) AS n
    FROM titles t
    WHERE t.original_language IS NOT NULL
      AND t.type = COALESCE(CAST(:media_type AS text), t.type)
    GROUP BY 1
""")

_language_rates: dict[str, tuple[datetime, dict[str, float]]] = {}


async def _catalog_language_rates(db: AsyncSession, media_type: str | None) -> dict[str, float]:
    """What share of the catalog each language is. The denominator, as with
    genres: without it every shelf is an English one."""
    cache_key = media_type or "all"
    now = datetime.now(UTC)
    cached = _language_rates.get(cache_key)
    if cached is not None and now - cached[0] < _BASE_RATE_TTL:
        return cached[1]

    rows = (await db.execute(_LANGUAGE_COUNTS, {"media_type": media_type})).all()
    total = sum(int(n) for _, n in rows) or 1
    rates = {str(code): int(n) / total for code, n in rows}
    _language_rates[cache_key] = (now, rates)
    return rates


async def affinity_languages(
    db: AsyncSession, user: User, media_type: str | None = None
) -> list[str]:
    """Where the things this person watches come from, when that is
    distinctive.

    This is the shelf someone means by "you are missing K-drama". Their taste
    vector already knows: a history full of Korean series sits near other
    Korean series. What it cannot do is say so on a row heading, and a row
    that says what it is gets clicked."""
    now = datetime.now(UTC)

    def recency(when: datetime) -> float:
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        days = max(0.0, (now - when).total_seconds() / 86400)
        return 0.5 ** (days / AFFINITY_HALF_LIFE_DAYS)

    watched = (
        select(Title.original_language, WatchEvent.watched_at)
        .join(WatchEvent, WatchEvent.title_id == Title.id)
        .where(WatchEvent.user_id == user.id)
    )
    liked = (
        select(Title.original_language, Interaction.created_at)
        .join(Interaction, Interaction.title_id == Title.id)
        .where(Interaction.user_id == user.id, Interaction.kind.in_(("like", "comment")))
    )
    if media_type in ("movie", "tv"):
        watched = watched.where(Title.type == media_type)
        liked = liked.where(Title.type == media_type)

    weights: dict[str, float] = {}
    total = 0.0
    for query in (watched, liked):
        for code, when in (await db.execute(query)).all():
            if not code:
                continue
            weight = recency(when)
            weights[code] = weights.get(code, 0.0) + weight
            total += weight
    if total <= 0:
        return []

    base = await _catalog_language_rates(db, media_type)
    ranked: list[tuple[float, str]] = []
    for code, weight in weights.items():
        # Only languages there is a name for. A heading is the entire point of
        # these rows, so a code we cannot put into words cannot have one, and
        # English is deliberately not in the list: an English shelf on an
        # English-majority catalog is just "more series" with extra steps.
        if code not in LANGUAGE_NAMES:
            continue
        if weight < MIN_LANGUAGE_WEIGHT:
            continue
        lift = (weight / total) / max(base.get(code, 0.002), 0.002)
        if lift < MIN_LANGUAGE_LIFT:
            continue
        ranked.append((lift, code))
    ranked.sort(reverse=True)
    return [code for _, code in ranked]


@dataclass
class Lens:
    """One way of reading the pool. The shelf is what comes back through it."""

    key: str
    title: str
    pick: Callable[[Title], bool]


def _language_pick(code: str) -> Callable[[Title], bool]:
    def pick(t: Title) -> bool:
        return t.original_language == code

    return pick


def _genre_pick(genre_id: int) -> Callable[[Title], bool]:
    def pick(t: Title) -> bool:
        return any(e.get("id") == genre_id for e in (t.genres or []))

    return pick


async def _lenses(
    db: AsyncSession,
    user: User,
    pool: taste_module.ScoredPool,
    media_type: str | None,
) -> list[Lens]:
    """Every lens, in the order they read best on a page.

    Built once and used by both the page and its "show me more", so a shelf
    cannot mean one thing on first load and something else on the second."""
    now_year = datetime.now(UTC).year
    lenses: list[Lens] = []

    # A named person is the most concrete reason a shelf can give.
    if pool.starring:
        names = await _followed_names(db, user)
        lenses.append(
            Lens("with-people-you-follow", _people_title(names), lambda t: t.id in pool.starring)
        )

    # Where their viewing comes from, before what it is about: someone who
    # watches K-drama thinks of that as the category, not "more mystery".
    for code in (await affinity_languages(db, user, media_type))[:LANGUAGE_SHELVES]:
        lenses.append(
            Lens(
                f"for-you-lang-{code}",
                # Filled in once the shelf exists, since the name depends on
                # what came back. A placeholder here would ship if the shelf
                # were empty, and an empty shelf is dropped anyway.
                "",
                _language_pick(code),
            )
        )

    for genre_id, genre_name in (await affinity_genres(db, user, media_type))[:GENRE_SHELVES]:
        lenses.append(
            Lens(
                f"for-you-genre-{genre_id}",
                f"More {genre_name.lower()} for you",
                _genre_pick(genre_id),
            )
        )

    lenses += [
        Lens(
            "fresh-for-you",
            "New, and your kind of thing",
            lambda t: t.year is not None and t.year >= now_year - FRESH_YEARS,
        ),
        Lens(
            "gems-for-you",
            "Hidden gems for you",
            lambda t: (
                taste_module.popularity_prior(t) <= GEM_MAX_POPULARITY
                and taste_module.quality_prior(t) >= GEM_MIN_QUALITY
            ),
        ),
        Lens(
            "vintage-for-you",
            "Older, and worth it",
            lambda t: t.year is not None and t.year <= now_year - VINTAGE_YEARS,
        ),
        Lens(
            "short-for-you",
            "Short enough for tonight",
            lambda t: t.type == "movie" and t.runtime is not None and t.runtime <= SHORT_RUNTIME,
        ),
        Lens(
            "acclaimed-for-you",
            "Very well reviewed, and your kind of thing",
            lambda t: taste_module.quality_prior(t) >= ACCLAIMED_MIN_QUALITY,
        ),
    ]
    return lenses


def _named(lens: Lens, titles: list[Title]) -> str:
    """The heading, once the contents are known."""
    if lens.title:
        return lens.title
    return _language_shelf_title(lens.key.rsplit("-", 1)[-1], titles)


@dataclass
class Context:
    """Everything the shelves are cut from, gathered once."""

    pool: taste_module.ScoredPool
    exclude: set[uuid.UUID]
    discovery: str


async def _context(
    db: AsyncSession, user: User, media_type: str | None, size: int = POOL
) -> Context | None:
    """Gather the taste vector, the exclusions and the candidate pool.

    None when there is nothing personal to say: AI off, or a person who has
    not told us anything yet. The caller falls back to trending, which is a
    better home page than an error."""
    try:
        vector = await taste_module.get_taste(db, user)
        if vector is None:
            return None

        # Seen already, rejected already, or impossible to watch tonight. The
        # last of those is not a detail: a shelf that opens on a film still
        # only playing in cinemas is not a suggestion, it is a thing to be
        # annoyed about, and the cinema page is where those belong.
        exclude = await taste_module.watched_title_ids(db, user)
        exclude |= await unwatchable_title_ids(db)

        prefs = user.prefs or {}
        followed = set(
            (
                await db.execute(
                    select(FollowedPerson.person_id).where(FollowedPerson.user_id == user.id)
                )
            )
            .scalars()
            .all()
        )
        pool = await taste_module.score_pool(
            db,
            vector,
            size,
            exclude,
            languages=prefs.get("languages") or None,
            followed_people=followed,
            media_type=media_type,
            on_services=_service_filter(user),
        )
    except (ai_client.AIDisabled, ai_client.AIError):
        return None
    if not pool:
        return None
    return Context(pool=pool, exclude=exclude, discovery=prefs.get("discovery") or "balanced")


def _service_filter(user: User) -> tuple[list[int], list[str]] | None:
    """The services this person actually pays for.

    On by default, because a suggestion you cannot press play on is not a
    suggestion: being shown a Netflix title when you do not have Netflix is
    an advert for someone else's product. Switchable off in Settings for
    anyone who wants to see everything.

    It needs both halves to mean anything, since availability is recorded
    per country, so an empty service list or no country at all leaves it off
    rather than silently emptying every shelf. That is what makes the
    default safe: a new account is unfiltered until it has said what it
    subscribes to."""
    prefs = user.prefs or {}
    if not prefs.get("only_my_services", True):
        return None
    services = [int(s) for s in (user.services or [])]
    countries = countries_for(user)
    if not services or not countries:
        return None
    return services, list(countries)


async def build_iter(
    db: AsyncSession,
    user: User,
    media_type: str | None = None,
) -> AsyncIterator[Shelf]:
    """Every personalized shelf, yielded the moment each one is ready.

    The expensive part — the pool — is computed once up front; each shelf
    after that is a cheap slice of it, so a consumer can put the first row
    on screen while the rest are still being cut."""
    context = await _context(db, user, media_type)
    if context is None:
        return
    pool = context.pool

    shelves: list[Shelf] = []
    used: set[uuid.UUID] = set()
    emitted = 0

    # The headline shelf shows whatever it has. The floor below applies to
    # the lenses, where three titles under "Hidden gems for you" is noise;
    # three titles here are still the best three answers we have, and a fresh
    # install with a small catalog should not look like the feature is
    # missing.
    main = [
        t
        for t, _ in taste_module.arrange(pool.items, MAIN_SHELF, context.discovery)
        if t.poster_path
    ]
    _add(shelves, used, "for-you", _main_title(media_type), main, minimum=1)
    for shelf in shelves[emitted:]:
        yield shelf
    emitted = len(shelves)

    # Straight after the headline, because these are the rows that answer
    # what the person did today. Everything below them is about who they are
    # in general, which changes far more slowly.
    #
    # Alone among the shelves, these neither read nor write the used set.
    # "Because you liked Coco" overlapping "Picked for you" is not a bug: they
    # are different questions, and the overlap is the honest answer to both.
    # Excluding one from the other only makes this row worse, since what it
    # would have to drop is precisely its best matches.
    shelves.extend(await _anchor_shelves(db, user, context.exclude, media_type))
    for shelf in shelves[emitted:]:
        yield shelf
    emitted = len(shelves)

    for lens in await _lenses(db, user, pool, media_type):
        titles = _take(pool.items, lens.pick, used)
        _add(shelves, used, lens.key, _named(lens, titles), titles)
        for shelf in shelves[emitted:]:
            yield shelf
        emitted = len(shelves)


async def build(
    db: AsyncSession,
    user: User,
    media_type: str | None = None,
) -> list[Shelf]:
    """Every personalized shelf for this person, in the order they read best."""
    return [shelf async for shelf in build_iter(db, user, media_type)]


async def page(
    db: AsyncSession,
    user: User,
    key: str,
    media_type: str | None = None,
    page_number: int = 1,
) -> Shelf | None:
    """More of one shelf.

    Forty is a lot of suggestions and still not all of them, so every shelf
    keeps going. The pool is widened in proportion to how deep the request
    goes, and the same lens is applied to it, so page two is the continuation
    of page one rather than a different question with a familiar heading.

    Reconstructed rather than remembered. A cursor would have to survive the
    taste vector changing underneath it, which it does every couple of hours
    by design, and stale pages of a shelf built from a taste you have moved
    on from is the wrong thing to be precise about."""
    if page_number < 1:
        return None
    # Deeper pages need a wider pool to cut from, but the top of it is
    # unchanged, so what page one showed is still what page one would show.
    context = await _context(db, user, media_type, size=POOL * (1 + page_number))
    if context is None:
        return None
    pool = context.pool

    if key == "for-you":
        want = MAIN_SHELF * (page_number + 1)
        arranged = [
            t for t, _ in taste_module.arrange(pool.items, want, context.discovery) if t.poster_path
        ]
        titles = arranged[MAIN_SHELF * page_number :]
        return Shelf(key=key, title=_main_title(media_type), titles=titles) if titles else None

    if key.startswith("because-"):
        for shelf in await _anchor_shelves(
            db, user, context.exclude, media_type, how_many=ANCHOR_SHELVES, depth=page_number + 1
        ):
            if shelf.key == key:
                titles = shelf.titles[SHELF * page_number :]
                return Shelf(key=key, title=shelf.title, titles=titles) if titles else None
        return None

    for lens in await _lenses(db, user, pool, media_type):
        if lens.key != key:
            continue
        titles = _take(pool.items, lens.pick, set(), limit=SHELF * (page_number + 1))
        rest = titles[SHELF * page_number :]
        return Shelf(key=key, title=_named(lens, titles), titles=rest) if rest else None
    return None


def _main_title(media_type: str | None) -> str:
    if media_type == "movie":
        return "Films picked for you"
    if media_type == "tv":
        return "Series picked for you"
    return "Picked for you"


def _people_title(names: list[str]) -> str:
    if not names:
        return "People you follow"
    if len(names) == 1:
        return f"Because you follow {names[0]}"
    return f"With {names[0]}, {names[1]} and others you follow"


async def _followed_names(db: AsyncSession, user: User) -> list[str]:
    return list(
        (
            await db.execute(
                select(FollowedPerson.name)
                .where(FollowedPerson.user_id == user.id)
                .order_by(FollowedPerson.created_at.desc())
                .limit(2)
            )
        )
        .scalars()
        .all()
    )
