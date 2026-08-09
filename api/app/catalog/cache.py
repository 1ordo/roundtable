"""Shared response cache for external catalog APIs.

Every upstream call goes through here so quota stays low and the app keeps
working when a provider is unreachable."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ApiCache


def _now() -> datetime:
    return datetime.now(UTC)


async def cache_get(db: AsyncSession, key: str, ttl_hours: int) -> dict | None:
    row = (await db.execute(select(ApiCache).where(ApiCache.key == key))).scalar_one_or_none()
    if row is None:
        return None
    fetched = row.fetched_at
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=UTC)
    if _now() - fetched > timedelta(hours=ttl_hours):
        return None
    return row.payload


async def cache_put(db: AsyncSession, key: str, payload: dict) -> None:
    source = key.split(":", 1)[0]
    stmt = pg_insert(ApiCache).values(key=key, source=source, payload=payload, fetched_at=_now())
    stmt = stmt.on_conflict_do_update(
        index_elements=[ApiCache.key], set_={"payload": payload, "fetched_at": _now()}
    )
    await db.execute(stmt)
    await db.flush()
