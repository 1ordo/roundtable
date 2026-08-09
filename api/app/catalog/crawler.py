"""Keep the catalog growing on its own.

Three jobs, all designed to run forever without ever finishing in a way
that leaves the library stuck:

  sweep      walk discovery pages in order, remembering where it stopped,
             so over days it works through the whole catalog
  refresh    revisit the oldest records so ratings, availability and
             certifications never go stale
  backfill   index anything that somehow has no vector

Everything is bounded per run and records its own progress, so a crash or
a restart resumes rather than starting over.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import ingest, tmdb
from app.models import FeatureFlag, Title

logger = logging.getLogger("watchpile.crawler")

# Where the sweep has reached, kept in the flags table so it survives
# restarts without needing its own migration.
CURSOR_KEY = "catalog_sweep_cursor"

# TMDB stops paging discovery at 500.
MAX_PAGE = 500

# Titles refreshed per run, and how old a record may get first.
REFRESH_BATCH = 40
REFRESH_AFTER = timedelta(days=7)


async def _cursor(db: AsyncSession) -> dict:
    row = (
        await db.execute(select(FeatureFlag).where(FeatureFlag.key == CURSOR_KEY))
    ).scalar_one_or_none()
    if row is None:
        row = FeatureFlag(key=CURSOR_KEY, enabled=True, config={"movie": 1, "tv": 1})
        db.add(row)
        await db.flush()
    return dict(row.config or {"movie": 1, "tv": 1})


async def _save_cursor(db: AsyncSession, cursor: dict) -> None:
    row = (
        await db.execute(select(FeatureFlag).where(FeatureFlag.key == CURSOR_KEY))
    ).scalar_one_or_none()
    if row is not None:
        row.config = cursor
        await db.flush()


async def sweep(db: AsyncSession, pages_per_type: int = 2) -> dict:
    """Take the next few discovery pages for each media type.

    Ordered by popularity descending and paged from where the last run
    stopped, so the catalog fills in from the most worth having downward
    and never repeats work it has already done."""
    cursor = await _cursor(db)
    added = 0
    seen = 0
    for media_type in ("movie", "tv"):
        page = int(cursor.get(media_type, 1))
        for _ in range(pages_per_type):
            if page > MAX_PAGE:
                # Wrap around and start freshening the head of the list.
                page = 1
            try:
                payload = await tmdb.discover(
                    db,
                    media_type,
                    {"sort_by": "popularity.desc", "page": page, "vote_count.gte": 20},
                )
            except (tmdb.TmdbNotConfigured, tmdb.TmdbError) as exc:
                logger.warning("sweep stopped at %s page %s: %s", media_type, page, exc)
                await _save_cursor(db, cursor)
                await db.commit()
                return {"added": added, "seen": seen, "stopped": True}

            for item in payload.get("results", []):
                seen += 1
                existing = (
                    await db.execute(
                        select(Title.id).where(
                            Title.tmdb_id == item["id"], Title.type == media_type
                        )
                    )
                ).first()
                if existing is not None:
                    continue
                try:
                    await ingest.ensure_title(db, media_type, item["id"])
                    added += 1
                except (tmdb.TmdbNotConfigured, tmdb.TmdbError):
                    continue
            page += 1
            cursor[media_type] = page
            await db.commit()

    await _save_cursor(db, cursor)
    await db.commit()
    logger.info("sweep added %d new titles from %d seen, cursor now %s", added, seen, cursor)
    return {"added": added, "seen": seen, "cursor": cursor, "stopped": False}


async def refresh_stale(db: AsyncSession, limit: int = REFRESH_BATCH) -> int:
    """Revisit the oldest records so nothing sits on week-old ratings or
    availability. Oldest first means the whole catalog rotates."""
    cutoff = datetime.now(UTC) - REFRESH_AFTER
    rows = (
        await db.execute(
            select(Title.tmdb_id, Title.type)
            .where((Title.details_refreshed_at.is_(None)) | (Title.details_refreshed_at < cutoff))
            .order_by(Title.details_refreshed_at.asc().nulls_first())
            .limit(limit)
        )
    ).all()
    done = 0
    for tmdb_id, media_type in rows:
        try:
            await ingest.ensure_title(db, media_type, tmdb_id, force=True)
            done += 1
        except (tmdb.TmdbNotConfigured, tmdb.TmdbError):
            break
    await db.commit()
    if done:
        logger.info("refreshed %d stale titles", done)
    return done


async def backfill_embeddings(db: AsyncSession, limit: int = 200) -> int:
    """Index anything that slipped through, so no title is invisible to the
    recommender."""
    from app.ai import client, embeddings

    try:
        await client.require_ai(db)
    except client.AIDisabled:
        return 0
    done = await embeddings.embed_missing_titles(db, limit=limit)
    await db.commit()
    return done


async def status(db: AsyncSession) -> dict:
    """What the crawler has achieved so far, for the admin page."""
    from app.models import TitleEmbedding

    total = (await db.execute(select(func.count(Title.id)))).scalar_one()
    indexed = (
        await db.execute(select(func.count(func.distinct(TitleEmbedding.title_id))))
    ).scalar_one()
    cutoff = datetime.now(UTC) - REFRESH_AFTER
    stale = (
        await db.execute(
            select(func.count(Title.id)).where(
                (Title.details_refreshed_at.is_(None)) | (Title.details_refreshed_at < cutoff)
            )
        )
    ).scalar_one()
    cursor = await _cursor(db)
    await db.commit()
    return {
        "titles": total,
        "indexed": indexed,
        "unindexed": max(0, total - indexed),
        "stale": stale,
        "cursor": cursor,
        "pages_done": int(cursor.get("movie", 1)) + int(cursor.get("tv", 1)) - 2,
        "pages_total": MAX_PAGE * 2,
    }
