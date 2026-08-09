import csv
import io
import json
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.audit import audit
from app.auth.deps import get_current_user
from app.db import get_db
from app.models import ListItem, User, WatchEvent
from app.tracking import service

router = APIRouter(prefix="/api/export")


def _neutralize(value):
    """Spreadsheets treat a leading =, +, -, or @ as a formula. Notes and
    list names come from other people, so prefix them into plain text."""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def _csv_response(rows: list[dict], filename: str) -> Response:
    buffer = io.StringIO()
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows([{k: _neutralize(v) for k, v in row.items()} for row in rows])
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _history_rows(db: AsyncSession, user: User) -> list[dict]:
    events = (
        (
            await db.execute(
                select(WatchEvent)
                .options(joinedload(WatchEvent.title))
                .where(WatchEvent.user_id == user.id)
                .order_by(WatchEvent.watched_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "name": e.title.name,
            "type": e.title.type,
            "year": e.title.year or "",
            "tmdb_id": e.title.tmdb_id,
            "imdb_id": e.title.imdb_id or "",
            "watched_at": e.watched_at.isoformat(),
            "rating_10": e.rating_10 if e.rating_10 is not None else "",
            "loved": e.loved,
            "source": e.source,
        }
        for e in events
    ]


async def _list_rows(db: AsyncSession, user: User) -> list[dict]:
    rows: list[dict] = []
    for lst in await service.visible_lists(db, user):
        items = (
            (
                await db.execute(
                    select(ListItem)
                    .options(joinedload(ListItem.title))
                    .where(ListItem.list_id == lst.id)
                    .order_by(ListItem.added_at)
                )
            )
            .scalars()
            .all()
        )
        rows.extend(
            {
                "list": lst.name,
                "list_kind": lst.kind,
                "name": item.title.name,
                "type": item.title.type,
                "year": item.title.year or "",
                "tmdb_id": item.title.tmdb_id,
                "imdb_id": item.title.imdb_id or "",
                "note": item.note or "",
                "added_at": item.added_at.isoformat(),
            }
            for item in items
        )
    return rows


@router.get("/history.csv")
async def export_history(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    rows = await _history_rows(db, user)
    await audit(db, "export.history", actor=user, request=request, detail={"rows": len(rows)})
    await db.commit()
    return _csv_response(rows, "watchpile-history.csv")


@router.get("/lists.csv")
async def export_lists(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    rows = await _list_rows(db, user)
    await audit(db, "export.lists", actor=user, request=request, detail={"rows": len(rows)})
    await db.commit()
    return _csv_response(rows, "watchpile-lists.csv")


@router.get("/all.json")
async def export_all(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    payload = {
        "exported_at": datetime.now().astimezone().isoformat(),
        "user": {"username": user.username, "email": user.email},
        "history": await _history_rows(db, user),
        "lists": await _list_rows(db, user),
    }
    await audit(db, "export.all", actor=user, request=request)
    await db.commit()
    return Response(
        json.dumps(payload, indent=2, default=str),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="watchpile-export.json"'},
    )
