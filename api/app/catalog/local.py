"""Local-catalog queries used when TMDB is not configured.

Keeps the app usable offline: whatever titles the database already holds
(seeded, imported, or previously fetched) still power home, browse, and
search instead of every page turning into a setup notice."""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Title


async def recent(db: AsyncSession, media_type: str | None = None, limit: int = 20) -> list[Title]:
    query = select(Title).order_by(Title.popularity.desc().nulls_last()).limit(limit)
    if media_type:
        query = query.where(Title.type == media_type)
    return list((await db.execute(query)).scalars())


async def newest(db: AsyncSession, limit: int = 20) -> list[Title]:
    """Most recently released titles we hold."""
    query = (
        select(Title)
        .where(Title.year.is_not(None))
        .order_by(Title.year.desc(), Title.popularity.desc().nulls_last())
        .limit(limit)
    )
    return list((await db.execute(query)).scalars())


async def top_rated(db: AsyncSession, limit: int = 20) -> list[Title]:
    """Highest rated titles that have enough votes to mean something."""
    query = (
        select(Title)
        .where(Title.tmdb_rating.is_not(None), Title.tmdb_votes > 5000)
        .order_by(Title.tmdb_rating.desc())
        .limit(limit)
    )
    return list((await db.execute(query)).scalars())


async def by_language(db: AsyncSession, code: str, limit: int = 20) -> list[Title]:
    query = (
        select(Title)
        .where(Title.original_language == code)
        .order_by(Title.popularity.desc().nulls_last())
        .limit(limit)
    )
    return list((await db.execute(query)).scalars())


async def by_genre(
    db: AsyncSession, media_type: str, genre_id: int, limit: int = 20
) -> list[Title]:
    query = (
        select(Title)
        .where(
            Title.type == media_type,
            Title.genres.contains([{"id": genre_id}]),
        )
        .order_by(Title.popularity.desc().nulls_last())
        .limit(limit)
    )
    return list((await db.execute(query)).scalars())


async def search(db: AsyncSession, term: str, limit: int = 40) -> list[Title]:
    pattern = f"%{term.strip()}%"
    query = (
        select(Title)
        .where(
            or_(
                Title.name.ilike(pattern),
                Title.original_name.ilike(pattern),
                Title.overview.ilike(pattern),
            )
        )
        .order_by(Title.popularity.desc().nulls_last())
        .limit(limit)
    )
    return list((await db.execute(query)).scalars())


async def genres(db: AsyncSession, media_type: str) -> list[dict]:
    """Distinct genres present in the local catalog, for the browse chips."""
    rows = (
        await db.execute(
            select(func.jsonb_array_elements(Title.genres).label("genre")).where(
                Title.type == media_type, func.jsonb_array_length(Title.genres) > 0
            )
        )
    ).scalars()
    seen: dict[int, str] = {}
    for row in rows:
        if isinstance(row, dict) and row.get("id") is not None:
            seen.setdefault(int(row["id"]), str(row.get("name", "")))
    return [{"id": gid, "name": name} for gid, name in sorted(seen.items(), key=lambda p: p[1])]


async def has_any(db: AsyncSession) -> bool:
    return (await db.execute(select(func.count(Title.id)))).scalar_one() > 0


async def browse(
    db: AsyncSession,
    media_type: str | None,
    genre_ids: list[int] | None = None,
    sort: str = "popular",
    limit: int = 60,
    language: str | None = None,
) -> list[Title]:
    """Browse the local catalog with the same knobs as the TMDB path, so
    losing the upstream connection changes the depth of the results and
    nothing about how the page behaves."""
    query = select(Title)
    if media_type:
        query = query.where(Title.type == media_type)
    if language:
        query = query.where(Title.original_language == language)
    if genre_ids:
        # Any of the ids: a combined label such as Action covers two genres
        # on the film side.
        query = query.where(or_(*[Title.genres.contains([{"id": gid}]) for gid in genre_ids]))
    if sort == "top":
        query = query.where(Title.tmdb_rating.is_not(None), Title.tmdb_votes > 200).order_by(
            Title.tmdb_rating.desc()
        )
    elif sort == "new":
        query = query.where(Title.year.is_not(None)).order_by(
            Title.year.desc(), Title.popularity.desc().nulls_last()
        )
    else:
        query = query.order_by(Title.popularity.desc().nulls_last())
    return list((await db.execute(query.limit(limit))).scalars())
