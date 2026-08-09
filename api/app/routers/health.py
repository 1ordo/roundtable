from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_admin
from app.db import get_db
from app.models import User

router = APIRouter(prefix="/api")


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict:
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}


class Showcase(BaseModel):
    """What the landing page shows. Deliberately nothing personal: this is
    the only endpoint served without a session, so it may only ever say
    what is in the catalog, never who watched it."""

    posters: list[str]
    titles: int
    # Distinct streaming services seen across every country, not people.
    services: int
    countries: int


@router.get("/public/showcase", response_model=Showcase)
async def showcase(db: AsyncSession = Depends(get_db)) -> Showcase:
    from app.models import Availability, Title

    rows = (
        (
            await db.execute(
                select(Title.poster_path)
                .where(Title.poster_path.is_not(None), Title.poster_path.like("/%"))
                .order_by(Title.popularity.desc().nulls_last())
                .limit(28)
            )
        )
        .scalars()
        .all()
    )
    total = (await db.execute(select(func.count(Title.id)))).scalar_one()
    countries = (
        await db.execute(select(func.count(func.distinct(Availability.country))))
    ).scalar_one()
    services = (
        await db.execute(select(func.count(func.distinct(Availability.provider_id))))
    ).scalar_one()
    return Showcase(
        posters=[p for p in rows if p],
        titles=int(total or 0),
        services=int(services or 0),
        countries=int(countries or 0),
    )


class ServiceState(BaseModel):
    name: str
    ok: bool
    detail: str


class StatusOut(BaseModel):
    """What this instance is doing, in plain terms.

    Admin only: it names which parts are down and how stale the catalog is,
    which is operational detail rather than something every member needs."""

    healthy: bool
    services: list[ServiceState]
    titles: int
    people_indexed: int
    countries: int
    services_tracked: int
    catalog_fresh_pct: int
    last_sweep: datetime | None
    version: str


@router.get("/status", response_model=StatusOut)
async def status(
    admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> StatusOut:
    from datetime import UTC, datetime, timedelta

    from app.catalog import crawler
    from app.config import get_settings
    from app.models import Availability, Title, TitleEmbedding

    checks: list[ServiceState] = []

    # The database answered, or this request would not be running.
    checks.append(ServiceState(name="Database", ok=True, detail="answering"))

    # Redis carries the worker queue and the sign-in limiter.
    redis_ok = True
    redis_detail = "answering"
    try:
        from redis.asyncio import Redis

        client = Redis.from_url(get_settings().redis_url)
        await client.ping()
        await client.aclose()
    except Exception as exc:  # noqa: BLE001 - any failure means unavailable
        redis_ok = False
        redis_detail = str(exc)[:80] or "not reachable"
    checks.append(ServiceState(name="Queue", ok=redis_ok, detail=redis_detail))

    settings = get_settings()
    checks.append(
        ServiceState(
            name="Catalog source",
            ok=bool(settings.tmdb_api_key or settings.tmdb_access_token),
            detail="TMDB configured" if settings.tmdb_api_key else "no TMDB key set",
        )
    )

    from app.ai import client as ai_client

    ai = await ai_client.get_ai_settings(db)
    checks.append(
        ServiceState(
            name="Assistant",
            ok=bool(ai.enabled and ai.api_key_enc),
            detail=(
                f"{ai.chat_model}"
                if ai.enabled and ai.api_key_enc
                else "off"
                if not ai.enabled
                else "no key set"
            ),
        )
    )

    titles = (await db.execute(select(func.count(Title.id)))).scalar_one()
    embedded = (await db.execute(select(func.count(TitleEmbedding.title_id)))).scalar_one()
    countries = (
        await db.execute(select(func.count(func.distinct(Availability.country))))
    ).scalar_one()
    providers = (
        await db.execute(select(func.count(func.distinct(Availability.provider_id))))
    ).scalar_one()

    # How much of the catalog has been refreshed recently enough to trust.
    cutoff = datetime.now(UTC) - timedelta(days=30)
    fresh = (
        await db.execute(select(func.count(Title.id)).where(Title.details_refreshed_at > cutoff))
    ).scalar_one()

    state = await crawler.status(db)
    await db.commit()

    return StatusOut(
        healthy=all(check.ok for check in checks),
        services=checks,
        titles=int(titles or 0),
        people_indexed=int(embedded or 0),
        countries=int(countries or 0),
        services_tracked=int(providers or 0),
        catalog_fresh_pct=round(100 * fresh / titles) if titles else 0,
        last_sweep=state.get("last_sweep") if isinstance(state, dict) else None,
        version=settings.version if hasattr(settings, "version") else "dev",
    )
