"""Episodes of a series: what exists, what you have seen, what is next.

Kept apart from tracking.py because a series is a different shape from a
film. A film is watched or it is not; a show is a position you are at, and
the only two questions worth answering are where that position is and what
comes after it.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import audit
from app.auth.deps import csrf_protect, get_current_user
from app.catalog import episodes as service
from app.catalog import ingest
from app.db import get_db
from app.models import Episode, Title, User, WatchEvent

router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])


class EpisodeOut(BaseModel):
    id: str
    season: int
    episode: int
    name: str | None
    overview: str | None
    air_date: date | None
    runtime: int | None
    still_path: str | None
    aired: bool
    watched: bool


class SeasonOut(BaseModel):
    season: int
    episodes: list[EpisodeOut]


class ShowEpisodes(BaseModel):
    seasons: list[SeasonOut]
    next_up: EpisodeOut | None
    aired: int
    watched: int
    upcoming: int
    complete: bool


class MarkBody(BaseModel):
    season: int
    episode: int
    watched: bool = True


class MarkSeasonBody(BaseModel):
    season: int
    watched: bool = True


async def _show(db: AsyncSession, tmdb_id: int) -> Title:
    title = await ingest.ensure_title(db, "tv", tmdb_id)
    if title is None:
        raise HTTPException(status_code=404, detail="series not found")
    return title


def _out(episode: Episode, seen: set, today: date) -> EpisodeOut:
    return EpisodeOut(
        id=str(episode.id),
        season=episode.season_number,
        episode=episode.episode_number,
        name=episode.name,
        overview=episode.overview,
        air_date=episode.air_date,
        runtime=episode.runtime,
        still_path=episode.still_path,
        aired=bool(episode.air_date and episode.air_date <= today),
        watched=episode.id in seen,
    )


@router.get("/titles/tv/{tmdb_id}/episodes", response_model=ShowEpisodes)
async def list_episodes(
    tmdb_id: int,
    viewer: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ShowEpisodes:
    """Every season of a show, with what you have already seen marked.

    Syncs from TMDB on first ask so a show nobody has opened still answers,
    then serves from the local table. Unaired episodes are returned rather
    than hidden, flagged so the interface can show what is coming without
    letting anyone tick it off.
    """
    from datetime import UTC, datetime

    show = await _show(db, tmdb_id)
    known = (
        await db.execute(select(Episode.id).where(Episode.title_id == show.id).limit(1))
    ).scalar_one_or_none()
    if known is None:
        await service.sync_series(db, show)
        await db.commit()

    rows = (
        (
            await db.execute(
                select(Episode)
                .where(Episode.title_id == show.id)
                .order_by(Episode.season_number, Episode.episode_number)
            )
        )
        .scalars()
        .all()
    )
    seen = await service.watched_episode_ids(db, viewer, show)
    today = datetime.now(UTC).date()

    buckets: dict[int, list[EpisodeOut]] = {}
    for row in rows:
        buckets.setdefault(row.season_number, []).append(_out(row, seen, today))

    upcoming = await service.next_up(db, viewer, show)
    stats = await service.progress(db, viewer, show)
    await db.commit()

    return ShowEpisodes(
        seasons=[SeasonOut(season=n, episodes=buckets[n]) for n in sorted(buckets)],
        next_up=_out(upcoming, seen, today) if upcoming is not None else None,
        aired=stats["aired"],
        watched=stats["watched"],
        upcoming=stats["upcoming"],
        complete=stats["complete"],
    )


@router.post(
    "/titles/tv/{tmdb_id}/episodes/watched",
    response_model=ShowEpisodes,
    dependencies=[Depends(csrf_protect)],
)
async def mark_episode(
    tmdb_id: int,
    body: MarkBody,
    viewer: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ShowEpisodes:
    """Tick one episode off, or untick it."""
    show = await _show(db, tmdb_id)
    episode = await service.find_episode(db, show, body.season, body.episode)
    if episode is None:
        await service.sync_series(db, show)
        await db.flush()
        episode = await service.find_episode(db, show, body.season, body.episode)
    if episode is None:
        raise HTTPException(status_code=404, detail="episode not found")

    if body.watched:
        # An episode that has not aired cannot have been watched, and
        # allowing it would corrupt both progress and next-up.
        from datetime import UTC, datetime

        if episode.air_date is None or episode.air_date > datetime.now(UTC).date():
            raise HTTPException(status_code=422, detail="that episode is not out yet")
        await service.mark_watched(db, viewer, show, episode)
    else:
        await db.execute(
            delete(WatchEvent).where(
                WatchEvent.user_id == viewer.id,
                WatchEvent.episode_id == episode.id,
            )
        )

    from app.ai import taste as taste_module

    await taste_module.invalidate_taste(db, viewer)
    await db.commit()
    return await list_episodes(tmdb_id, viewer, db)


@router.post(
    "/titles/tv/{tmdb_id}/episodes/season",
    response_model=ShowEpisodes,
    dependencies=[Depends(csrf_protect)],
)
async def mark_season(
    tmdb_id: int,
    body: MarkSeasonBody,
    request_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ShowEpisodes:
    """Tick off a whole season, or untick it.

    Only aired episodes are affected either way, so marking a season that is
    still going does not silently claim the rest of it.
    """
    from datetime import UTC, datetime

    show = await _show(db, tmdb_id)
    today = datetime.now(UTC).date()
    rows = (
        (
            await db.execute(
                select(Episode).where(
                    Episode.title_id == show.id,
                    Episode.season_number == body.season,
                    Episode.air_date.is_not(None),
                    Episode.air_date <= today,
                )
            )
        )
        .scalars()
        .all()
    )
    for episode in rows:
        if body.watched:
            await service.mark_watched(db, request_user, show, episode)
        else:
            await db.execute(
                delete(WatchEvent).where(
                    WatchEvent.user_id == request_user.id,
                    WatchEvent.episode_id == episode.id,
                )
            )

    await audit(db, "episodes.season", actor=request_user, object_id=str(show.tmdb_id))
    from app.ai import taste as taste_module

    await taste_module.invalidate_taste(db, request_user)
    await db.commit()
    return await list_episodes(tmdb_id, request_user, db)
