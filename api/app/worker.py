"""arq worker. Job functions land here milestone by milestone; the heartbeat
cron proves the queue wiring end to end from day one."""

import logging
import uuid

from arq import cron
from arq.connections import RedisSettings

from app.config import get_settings

logger = logging.getLogger("watchpile.worker")


async def heartbeat(ctx: dict) -> None:
    logger.info("worker heartbeat ok")


async def process_import_batch(ctx: dict, batch_id: str) -> None:
    from app.db import get_sessionmaker
    from app.imports.service import process_batch

    async with get_sessionmaker()() as db:
        await process_batch(db, uuid.UUID(batch_id))


async def poll_availability(ctx: dict) -> None:
    from app.db import get_sessionmaker
    from app.notifications.service import notify_new_franchise_parts
    from app.notifications.service import poll_availability as run_poll

    async with get_sessionmaker()() as db:
        await run_poll(db)
        # A sequel to something they loved is worth the same word as a new
        # arrival on their services.
        await notify_new_franchise_parts(db)


async def poll_episodes(ctx: dict) -> None:
    """Refresh episode lists and tell people when a new one is out."""
    from app.db import get_sessionmaker
    from app.notifications.service import notify_new_episodes

    async with get_sessionmaker()() as db:
        result = await notify_new_episodes(db)
        if result["notifications"]:
            logger.info("new episodes: %s", result)


async def ai_maintenance(ctx: dict) -> None:
    """Embed new titles and compute vibe tags. A no-op while AI is disabled."""
    from app.ai import embeddings
    from app.ai.client import AIDisabled, AIError
    from app.db import get_sessionmaker

    async with get_sessionmaker()() as db:
        try:
            await embeddings.embed_missing_titles(db)
            await embeddings.tag_untagged_titles(db)
        except AIDisabled:
            pass
        except AIError:
            logger.warning("ai maintenance skipped: endpoint unavailable")


async def sweep_catalog(ctx: dict) -> None:
    """Walk the catalog a few pages at a time, remembering the position, so
    it fills in continuously instead of re-fetching the same head."""
    from app.catalog import crawler
    from app.db import get_sessionmaker

    async with get_sessionmaker()() as db:
        result = await crawler.sweep(db, pages_per_type=3)
        logger.info("catalog sweep: %s", result)


async def refresh_catalog(ctx: dict) -> None:
    """Rotate through the oldest records so nothing goes stale."""
    from app.catalog import crawler
    from app.db import get_sessionmaker

    async with get_sessionmaker()() as db:
        await crawler.refresh_stale(db)
        await crawler.backfill_embeddings(db)


async def ask_night_verdicts(ctx: dict) -> None:
    """Ask everyone what they thought once the wait after a night is over.

    A schedule rather than a timer per night, so nothing is lost across a
    restart and a night that was marked watched while the worker was down
    still gets its question."""
    from app.db import get_sessionmaker
    from app.routers import nights

    async with get_sessionmaker()() as db:
        result = await nights.ask_for_verdicts(db)
        if result["asked"]:
            logger.info("night verdicts: %s", result)


async def poll_followed_people(ctx: dict) -> None:
    """New work from actors and directors people follow."""
    from app.db import get_sessionmaker
    from app.notifications import service

    async with get_sessionmaker()() as db:
        await service.watch_followed_people(db)


async def expense_reminders(ctx: dict) -> None:
    """One quiet word per lapsed subscription per cycle, for opted-in users."""
    from app.db import get_sessionmaker
    from app.tracking.expenses import remind_idle_services

    async with get_sessionmaker()() as db:
        await remind_idle_services(db)
        await db.commit()


async def poll_cinema(ctx: dict) -> None:
    """Tell people when a film they are waiting for reaches cinemas."""
    from app.db import get_sessionmaker
    from app.routers import cinema

    async with get_sessionmaker()() as db:
        result = await cinema.alert_on_openings(db)
        if result["notified"]:
            logger.info("cinema openings: %s", result)


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    functions = [process_import_batch]
    cron_jobs = [
        cron(heartbeat, hour=None, minute=0),
        # Daily availability sweep, early morning UTC.
        cron(poll_availability, hour=5, minute=15),
        cron(expense_reminders, hour=8, minute=40),
        # Grow the catalog continuously rather than once a day, so it keeps
        # filling in between visits instead of getting stuck.
        cron(sweep_catalog, hour=None, minute={5, 25, 45}),
        # Keep what is already here current, and index any stragglers.
        cron(refresh_catalog, hour=None, minute={15, 50}),
        cron(ai_maintenance, hour=None, minute=35),
        # Every twenty minutes: fine enough that a survey set to zero hours
        # arrives while the evening is still fresh.
        cron(ask_night_verdicts, hour=None, minute={0, 20, 40}),
        # Once a day is plenty: a cast list does not change hourly.
        cron(poll_followed_people, hour=6, minute=10),
        # Hourly. The alert goes out a week before a film opens, so the exact
        # hour hardly matters, but running often means someone who tracks a
        # film inside that week hears within the hour instead of the next day.
        # The job only spends a TMDB call on films near their window, so the
        # cadence costs little.
        cron(poll_cinema, hour=None, minute=20),
        # Episodes land at all hours and in every timezone, so checking twice
        # a day would mean telling someone about last night's episode at
        # lunchtime. Hourly, offset from the other sweeps, and the season
        # fetch is cached for six hours so a finished show costs nothing.
        cron(poll_episodes, hour=None, minute=40),
    ]
    # arq cancels a job after 300s by default and cron jobs are not retried,
    # so a sweep over a large instance would be killed halfway with nothing
    # in the log to say so.
    job_timeout = 900
