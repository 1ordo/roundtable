import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth.deps import csrf_protect, get_current_user
from app.catalog import ingest, tmdb
from app.db import get_db
from app.models import List, ListItem, Title, User, WatchEvent
from app.routers.catalog import TitleCard, invalidate_home
from app.tracking import service

router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user), Depends(csrf_protect)])


def _card(title: Title) -> TitleCard:
    return TitleCard(
        tmdb_id=title.tmdb_id,
        type=title.type,
        name=title.name,
        poster_path=title.poster_path,
        backdrop_path=title.backdrop_path,
        year=title.year,
        tmdb_rating=title.tmdb_rating,
    )


class ListSummary(BaseModel):
    id: str
    name: str
    kind: str
    count: int
    posters: list[str]


class ListsResponse(BaseModel):
    lists: list[ListSummary]


@router.get("/lists", response_model=ListsResponse)
async def my_lists(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> ListsResponse:
    lists = await service.visible_lists(db, user)
    summaries = []
    for lst in lists:
        count = (
            await db.execute(select(func.count(ListItem.id)).where(ListItem.list_id == lst.id))
        ).scalar_one()
        posters = (
            (
                await db.execute(
                    select(Title.poster_path)
                    .join(ListItem, ListItem.title_id == Title.id)
                    .where(ListItem.list_id == lst.id, Title.poster_path.is_not(None))
                    .order_by(ListItem.added_at.desc())
                    .limit(3)
                )
            )
            .scalars()
            .all()
        )
        summaries.append(
            ListSummary(
                id=str(lst.id),
                name=lst.name,
                kind=lst.kind,
                count=count,
                posters=[p for p in posters if p is not None],
            )
        )
    await db.commit()
    return ListsResponse(lists=summaries)


class CreateListBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@router.post("/lists", response_model=ListSummary, status_code=201)
async def create_list(
    body: CreateListBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ListSummary:
    lst = List(tenant_id=user.tenant_id, user_id=user.id, name=body.name.strip(), kind="custom")
    db.add(lst)
    await db.flush()
    await db.commit()
    return ListSummary(id=str(lst.id), name=lst.name, kind=lst.kind, count=0, posters=[])


async def _get_list(db: AsyncSession, list_id: str, user: User) -> List:
    try:
        lid = uuid.UUID(list_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="list not found") from exc
    lst = (await db.execute(select(List).where(List.id == lid))).scalar_one_or_none()
    if lst is None or not service.can_touch_list(user, lst):
        raise HTTPException(status_code=404, detail="list not found")
    return lst


@router.delete("/lists/{list_id}", status_code=204)
async def delete_list(
    list_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    lst = await _get_list(db, list_id, user)
    if lst.kind != "custom":
        raise HTTPException(status_code=400, detail="only custom lists can be deleted")
    await db.delete(lst)
    await db.commit()


class ListItemOut(BaseModel):
    title: TitleCard
    note: str | None
    added_by: str | None
    added_at: datetime


class ListDetailResponse(BaseModel):
    id: str
    name: str
    kind: str
    items: list[ListItemOut]


@router.get("/lists/{list_id}/items", response_model=ListDetailResponse)
async def list_items(
    list_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ListDetailResponse:
    lst = await _get_list(db, list_id, user)
    rows = (
        (
            await db.execute(
                select(ListItem)
                .options(joinedload(ListItem.title))
                .where(ListItem.list_id == lst.id)
                .order_by(ListItem.added_at.desc())
            )
        )
        .scalars()
        .all()
    )
    usernames = {
        uid: name for uid, name in (await db.execute(select(User.id, User.username))).all()
    }
    return ListDetailResponse(
        id=str(lst.id),
        name=lst.name,
        kind=lst.kind,
        items=[
            ListItemOut(
                title=_card(row.title),
                note=row.note,
                added_by=usernames.get(row.added_by),
                added_at=row.added_at,
            )
            for row in rows
        ],
    )


class AddItemBody(BaseModel):
    type: str = Field(pattern="^(movie|tv)$")
    tmdb_id: int
    note: str | None = Field(default=None, max_length=500)


@router.post("/lists/{list_id}/items", status_code=201)
async def add_item(
    list_id: str,
    body: AddItemBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    lst = await _get_list(db, list_id, user)
    try:
        title = await ingest.ensure_title(db, body.type, body.tmdb_id)
    except (tmdb.TmdbNotConfigured, tmdb.TmdbError) as exc:
        raise HTTPException(status_code=503, detail="catalog unavailable") from exc
    await service.add_title_to_list(db, lst, title.id, user, body.note)
    await db.commit()
    await invalidate_home(str(user.id))
    return {"status": "added"}


@router.delete("/lists/{list_id}/items/{media_type}/{tmdb_id}", status_code=204)
async def remove_item(
    list_id: str,
    media_type: str,
    tmdb_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    lst = await _get_list(db, list_id, user)
    title = (
        await db.execute(select(Title).where(Title.tmdb_id == tmdb_id, Title.type == media_type))
    ).scalar_one_or_none()
    if title is None:
        raise HTTPException(status_code=404, detail="title not found")
    item = (
        await db.execute(
            select(ListItem).where(ListItem.list_id == lst.id, ListItem.title_id == title.id)
        )
    ).scalar_one_or_none()
    if item is not None:
        await db.delete(item)
    await db.commit()


class WatchBody(BaseModel):
    type: str = Field(pattern="^(movie|tv)$")
    tmdb_id: int
    watched_at: datetime | None = None
    rating_10: int | None = Field(default=None, ge=1, le=10)
    loved: bool = False


class WatchEventOut(BaseModel):
    id: str
    title: TitleCard
    watched_at: datetime
    rating_10: int | None
    loved: bool
    source: str


@router.post("/history", response_model=WatchEventOut, status_code=201)
async def mark_watched(
    body: WatchBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WatchEventOut:
    try:
        title = await ingest.ensure_title(db, body.type, body.tmdb_id)
    except (tmdb.TmdbNotConfigured, tmdb.TmdbError) as exc:
        raise HTTPException(status_code=503, detail="catalog unavailable") from exc
    event = WatchEvent(
        user_id=user.id,
        title_id=title.id,
        rating_10=body.rating_10,
        loved=body.loved,
        source="app",
    )
    if body.watched_at is not None:
        event.watched_at = body.watched_at
    db.add(event)
    await db.flush()
    await db.refresh(event)  # load the server-side watched_at default
    await db.commit()
    await invalidate_home(str(user.id))
    return WatchEventOut(
        id=str(event.id),
        title=_card(title),
        watched_at=event.watched_at,
        rating_10=event.rating_10,
        loved=event.loved,
        source=event.source,
    )


class HistoryPage(BaseModel):
    total: int
    events: list[WatchEventOut]


@router.get("/history", response_model=HistoryPage)
async def history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
) -> HistoryPage:
    total = (
        await db.execute(select(func.count(WatchEvent.id)).where(WatchEvent.user_id == user.id))
    ).scalar_one()
    rows = (
        (
            await db.execute(
                select(WatchEvent)
                .options(joinedload(WatchEvent.title))
                .where(WatchEvent.user_id == user.id)
                .order_by(WatchEvent.watched_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return HistoryPage(
        total=total,
        events=[
            WatchEventOut(
                id=str(e.id),
                title=_card(e.title),
                watched_at=e.watched_at,
                rating_10=e.rating_10,
                loved=e.loved,
                source=e.source,
            )
            for e in rows
        ],
    )


class UpdateEventBody(BaseModel):
    rating_10: int | None = Field(default=None, ge=1, le=10)
    loved: bool | None = None
    watched_at: datetime | None = None


async def _get_event(db: AsyncSession, event_id: str, user: User) -> WatchEvent:
    try:
        eid = uuid.UUID(event_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="event not found") from exc
    event = (
        await db.execute(
            select(WatchEvent)
            .options(joinedload(WatchEvent.title))
            .where(WatchEvent.id == eid, WatchEvent.user_id == user.id)
        )
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    return event


@router.patch("/history/{event_id}", response_model=WatchEventOut)
async def update_event(
    event_id: str,
    body: UpdateEventBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WatchEventOut:
    event = await _get_event(db, event_id, user)
    if body.rating_10 is not None:
        event.rating_10 = body.rating_10
    if body.loved is not None:
        event.loved = body.loved
    if body.watched_at is not None:
        event.watched_at = body.watched_at
    await db.commit()
    await invalidate_home(str(user.id))
    return WatchEventOut(
        id=str(event.id),
        title=_card(event.title),
        watched_at=event.watched_at,
        rating_10=event.rating_10,
        loved=event.loved,
        source=event.source,
    )


@router.delete("/history/{event_id}", status_code=204)
async def delete_event(
    event_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    event = await _get_event(db, event_id, user)
    await db.delete(event)
    await db.commit()
    await invalidate_home(str(user.id))


class TitleState(BaseModel):
    lists: list[str]  # list ids containing this title
    watched_count: int
    my_rating: int | None
    loved: bool


@router.get("/titles/{media_type}/{tmdb_id}/state", response_model=TitleState)
async def title_state(
    media_type: str,
    tmdb_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TitleState:
    title = (
        await db.execute(select(Title).where(Title.tmdb_id == tmdb_id, Title.type == media_type))
    ).scalar_one_or_none()
    if title is None:
        return TitleState(lists=[], watched_count=0, my_rating=None, loved=False)
    visible = await service.visible_lists(db, user)
    visible_ids = [lst.id for lst in visible]
    in_lists = (
        (
            await db.execute(
                select(ListItem.list_id).where(
                    ListItem.title_id == title.id, ListItem.list_id.in_(visible_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    events = (
        (
            await db.execute(
                select(WatchEvent)
                .where(WatchEvent.user_id == user.id, WatchEvent.title_id == title.id)
                .order_by(WatchEvent.watched_at.desc())
            )
        )
        .scalars()
        .all()
    )
    await db.commit()
    return TitleState(
        lists=[str(lid) for lid in in_lists],
        watched_count=len(events),
        my_rating=next((e.rating_10 for e in events if e.rating_10 is not None), None),
        loved=any(e.loved for e in events),
    )
