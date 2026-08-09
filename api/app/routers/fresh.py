from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.catalog import local, services, tmdb
from app.db import get_db
from app.models import Availability, Title, User
from app.routers.catalog import (
    HomeRow,
    TitleCard,
    _attach_match_scores,
    _card_from_title,
    _cards,
)

router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])

NEW_ON_SERVICES_DAYS = 30


class ServiceOut(BaseModel):
    id: int
    name: str
    color: str
    note: str | None = None
    subscribed: bool
    # The provider's own logo, so the picker is recognisable at a glance.
    logo_path: str | None = None
    # False when the catalog carries no listings for this service at all, so
    # the UI can say that rather than imply there is simply nothing new.
    tracked: bool = True


class ServiceSection(BaseModel):
    service: ServiceOut
    items: list[TitleCard]
    # True when we hold no availability data for this service yet.
    unknown: bool


class NewResponse(BaseModel):
    rows: list[HomeRow]
    services: list[ServiceSection]
    showing_all_services: bool


async def _service_logos(db: AsyncSession, country: str | None) -> dict[int, str]:
    """Provider logos, taken from the catalog's own provider directory.

    Regions are merged rather than tried in turn: a service that is not sold
    in this country still deserves its logo in the picker, and that art only
    appears in the regions where it operates."""
    logos: dict[int, str] = {}
    regions = [region for region in (country, "US", "GB") if region]
    for region in dict.fromkeys(regions):
        try:
            payload = await tmdb.provider_list(db, region)
        except (tmdb.TmdbNotConfigured, tmdb.TmdbError):
            continue
        for provider in payload.get("results", []):
            pid, logo = provider.get("provider_id"), provider.get("logo_path")
            if pid is not None and logo:
                logos.setdefault(pid, logo)
    return logos


@router.get("/services", response_model=list[ServiceOut])
async def list_services(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[ServiceOut]:
    mine = set(user.services or [])
    logos = await _service_logos(db, user.country_code)
    await db.commit()
    out = []
    for s in services.SERVICES:
        # A service answers to several provider ids; use whichever has art.
        logo = next((logos[pid] for pid in s["ids"] if pid in logos), None)
        out.append(
            ServiceOut(
                id=s["id"],
                name=s["name"],
                color=s["color"],
                note=s.get("note"),
                subscribed=s["id"] in mine,
                logo_path=logo,
                tracked=any(pid in logos for pid in s["ids"]),
            )
        )
    return out


async def _service_sections(db: AsyncSession, user: User, show_all: bool) -> list[ServiceSection]:
    """One section per streaming service.

    By default only the services this person pays for, because a row they
    cannot press play on is noise."""
    mine = set(user.services or [])
    logos = await _service_logos(db, user.country_code)
    wanted = (
        services.SERVICES
        if show_all or not mine
        else [s for s in services.SERVICES if s["id"] in mine]
    )
    since = datetime.now(UTC) - timedelta(days=NEW_ON_SERVICES_DAYS)

    sections: list[ServiceSection] = []
    for service in wanted:
        query = (
            select(Title)
            .join(Availability, Availability.title_id == Title.id)
            .where(
                # TMDB reports one service under several provider ids.
                Availability.provider_id.in_(service["ids"]),
                Availability.kind.in_(["stream", "free", "ads"]),
                Availability.first_seen_at >= since,
            )
            .order_by(Availability.first_seen_at.desc())
            .limit(20)
        )
        if user.country_code:
            query = query.where(Availability.country == user.country_code)
        found = list((await db.execute(query)).scalars().unique())
        sections.append(
            ServiceSection(
                service=ServiceOut(
                    id=service["id"],
                    name=service["name"],
                    color=service["color"],
                    note=service.get("note"),
                    subscribed=service["id"] in mine,
                    logo_path=next((logos[pid] for pid in service["ids"] if pid in logos), None),
                    tracked=any(pid in logos for pid in service["ids"]),
                ),
                items=[_card_from_title(t) for t in found],
                unknown=not found,
            )
        )
    return sections


@router.get("/new", response_model=NewResponse)
async def whats_new(
    all_services: bool = Query(default=False, alias="all"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NewResponse:
    rows: list[HomeRow] = []

    try:
        region = user.country_code
        rows.append(
            HomeRow(
                key="in-theaters",
                title="In theaters now",
                items=_cards(await tmdb.now_playing(db, region), "movie"),
            )
        )
        rows.append(
            HomeRow(
                key="upcoming",
                title="Coming soon",
                items=_cards(await tmdb.upcoming(db, region), "movie"),
            )
        )
        rows.append(
            HomeRow(
                key="new-series",
                title="Series on the air",
                items=_cards(await tmdb.on_the_air(db), "tv"),
            )
        )
    except (tmdb.TmdbNotConfigured, tmdb.TmdbError) as exc:
        # Without a release feed, the newest honest thing is what arrived in
        # the catalog most recently.
        recent = await local.newest(db, limit=20)
        if recent:
            rows.append(
                HomeRow(
                    key="recently-added",
                    title="Recently added",
                    items=[_card_from_title(t) for t in recent],
                )
            )
        best = await local.top_rated(db, limit=20)
        if best:
            rows.append(
                HomeRow(
                    key="best-rated",
                    title="Best rated in your catalog",
                    items=[_card_from_title(t) for t in best],
                )
            )
        sections = await _service_sections(db, user, all_services)
        if not rows and not sections:
            detail = (
                "tmdb_not_configured"
                if isinstance(exc, tmdb.TmdbNotConfigured)
                else "tmdb_unavailable"
            )
            status = 503 if isinstance(exc, tmdb.TmdbNotConfigured) else 502
            raise HTTPException(status_code=status, detail=detail) from exc
        await _attach_match_scores(db, user, rows)
        await db.commit()
        return NewResponse(rows=rows, services=sections, showing_all_services=all_services)

    sections = await _service_sections(db, user, all_services)
    await _attach_match_scores(db, user, rows)
    await db.commit()
    return NewResponse(rows=rows, services=sections, showing_all_services=all_services)
