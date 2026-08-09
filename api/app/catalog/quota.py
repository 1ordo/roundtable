"""Daily request counters for external APIs, upserted per call. The admin
quota view and the OMDb budget guard both read from here."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_sessionmaker
from app.models import QuotaUsage


async def bump(db: AsyncSession, source: str, amount: int = 1) -> None:
    """Increment today's counter in its own short transaction.

    The caller's session stays open across external HTTP calls, and holding
    this single hot row's lock for that long would serialize every request
    that touches TMDB. A separate connection commits immediately instead."""
    today = datetime.now(UTC).date()
    stmt = pg_insert(QuotaUsage).values(source=source, day=today, count=amount)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_quota_usage_source_day",
        set_={"count": QuotaUsage.count + amount},
    )
    async with get_sessionmaker()() as counter_session:
        await counter_session.execute(stmt)
        await counter_session.commit()


async def used_today(db: AsyncSession, source: str) -> int:
    today = datetime.now(UTC).date()
    row = await db.execute(
        select(QuotaUsage.count).where(QuotaUsage.source == source, QuotaUsage.day == today)
    )
    return row.scalar_one_or_none() or 0
