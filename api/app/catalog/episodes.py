"""Episodes: keeping them current, and knowing where someone is in a show.

A series used to be one row, which cannot answer either of the two questions
people have about a show they are watching: what have I already seen, and
what do I put on next. Both are answered here.

Two rules shape this module:

  aired is not the same as released   an episode with no air date, or one
                                      dated in the future, is not something
                                      anyone can have watched, so it never
                                      counts toward progress and never
                                      triggers an alert.
  specials do not block a show        TMDB calls them season 0. They are
                                      real episodes people may want to log,
                                      but "next up" must never point at one,
                                      because a special nobody knew about
                                      would stall the whole series forever.
"""

import logging
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import tmdb
from app.models import Episode, Title, User, WatchEvent

logger = logging.getLogger("roundtable.episodes")

# Season 0 is TMDB's specials bucket.
SPECIALS = 0


def _as_date(value: object) -> date | None:
    text = str(value or "")[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def season_numbers(payload: dict) -> list[int]:
    """Which seasons a series has, from a details payload."""
    out: list[int] = []
    for entry in payload.get("seasons") or []:
        number = entry.get("season_number")
        if isinstance(number, int):
            out.append(number)
    return sorted(set(out))


async def sync_series(db: AsyncSession, title: Title, payload: dict | None = None) -> int:
    """Bring one series' episode list up to date. Returns rows written.

    Upserts rather than replacing, so a watch pointing at an episode is
    never orphaned by a refresh. TMDB renumbering an episode is rare enough,
    and destructive enough to someone's history, that letting the old row
    stand is the safer failure.
    """
    if title.type != "tv":
        return 0
    if payload is None:
        payload = title.raw_tmdb or {}
        if not payload.get("seasons"):
            try:
                payload = await tmdb.details(db, "tv", title.tmdb_id)
            except (tmdb.TmdbNotConfigured, tmdb.TmdbError):
                return 0

    written = 0
    now = datetime.now(UTC)
    for number in season_numbers(payload):
        try:
            season = await tmdb.season(db, title.tmdb_id, number)
        except (tmdb.TmdbNotConfigured, tmdb.TmdbError):
            logger.info("episodes: season %s of %s unavailable", number, title.name)
            continue
        for entry in season.get("episodes") or []:
            episode_number = entry.get("episode_number")
            if not isinstance(episode_number, int):
                continue
            values = {
                "title_id": title.id,
                "tmdb_id": entry.get("id"),
                "season_number": number,
                "episode_number": episode_number,
                "name": (entry.get("name") or None),
                "overview": (entry.get("overview") or None),
                "air_date": _as_date(entry.get("air_date")),
                "runtime": entry.get("runtime"),
                "still_path": entry.get("still_path"),
                "refreshed_at": now,
            }
            stmt = pg_insert(Episode).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[
                    Episode.title_id,
                    Episode.season_number,
                    Episode.episode_number,
                ],
                set_={k: v for k, v in values.items() if k != "title_id"},
            )
            await db.execute(stmt)
            written += 1
    return written


async def aired_episodes(
    db: AsyncSession, title: Title, today: date | None = None
) -> list[Episode]:
    """Every episode of a series that has actually gone out, in order."""
    today = today or datetime.now(UTC).date()
    rows = (
        (
            await db.execute(
                select(Episode)
                .where(
                    Episode.title_id == title.id,
                    Episode.air_date.is_not(None),
                    Episode.air_date <= today,
                )
                .order_by(Episode.season_number, Episode.episode_number)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def watched_episode_ids(db: AsyncSession, user: User, title: Title) -> set[uuid.UUID]:
    rows = (
        (
            await db.execute(
                select(WatchEvent.episode_id).where(
                    WatchEvent.user_id == user.id,
                    WatchEvent.title_id == title.id,
                    WatchEvent.episode_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    return {row for row in rows if row is not None}


async def next_up(db: AsyncSession, user: User, title: Title) -> Episode | None:
    """The episode to put on next: the earliest aired one not yet watched.

    Specials are skipped. Someone who has seen every regular episode should
    be told they are up to date, not sent to a 2009 Christmas special they
    have never heard of.
    """
    seen = await watched_episode_ids(db, user, title)
    for episode in await aired_episodes(db, title):
        if episode.season_number == SPECIALS:
            continue
        if episode.id not in seen:
            return episode
    return None


async def progress(db: AsyncSession, user: User, title: Title) -> dict:
    """How far through a series someone is, counting only what has aired."""
    aired = [e for e in await aired_episodes(db, title) if e.season_number != SPECIALS]
    seen = await watched_episode_ids(db, user, title)
    watched = sum(1 for e in aired if e.id in seen)
    upcoming = (
        await db.execute(
            select(func.count(Episode.id)).where(
                Episode.title_id == title.id,
                Episode.air_date.is_not(None),
                Episode.air_date > datetime.now(UTC).date(),
            )
        )
    ).scalar_one()
    return {
        "aired": len(aired),
        "watched": watched,
        "upcoming": int(upcoming),
        "complete": bool(aired) and watched == len(aired),
    }


async def mark_watched(
    db: AsyncSession,
    user: User,
    title: Title,
    episode: Episode,
    source: str = "app",
) -> bool:
    """Log one episode. Returns False when it was already logged.

    Idempotent on purpose: the extension can report the same episode more
    than once, and a rewatch is a different thing from a double count.
    """
    existing = (
        await db.execute(
            select(WatchEvent).where(
                WatchEvent.user_id == user.id,
                WatchEvent.episode_id == episode.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return False
    db.add(
        WatchEvent(
            user_id=user.id,
            title_id=title.id,
            episode_id=episode.id,
            source=source,
        )
    )
    return True


async def find_episode(
    db: AsyncSession, title: Title, season_number: int, episode_number: int
) -> Episode | None:
    return (
        await db.execute(
            select(Episode).where(
                Episode.title_id == title.id,
                Episode.season_number == season_number,
                Episode.episode_number == episode_number,
            )
        )
    ).scalar_one_or_none()
