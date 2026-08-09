import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import audit
from app.auth.deps import csrf_protect, get_current_user
from app.db import get_db
from app.imports import parsers, queue
from app.imports import service as import_service
from app.models import ImportBatch, User

router = APIRouter(
    prefix="/api/imports", dependencies=[Depends(get_current_user), Depends(csrf_protect)]
)

MAX_IMPORT_BYTES = 10 * 1024 * 1024

PARSERS = {
    "netflix_history": parsers.parse_netflix_history,
    "netflix_mylist": parsers.parse_netflix_mylist,
    "json": parsers.parse_json_payload,
}

DEFAULT_TARGET = {
    "netflix_history": "history",
    "netflix_mylist": "watchlist",
    "json": "watchlist",
}


class BatchOut(BaseModel):
    id: str
    service: str
    target: str
    filename: str | None
    status: str
    error: str | None
    stats: dict
    pending_review: int
    created_at: datetime


def _batch_out(batch: ImportBatch) -> BatchOut:
    pending = sum(1 for e in (batch.review_queue or []) if not e.get("resolved"))
    return BatchOut(
        id=str(batch.id),
        service=batch.service,
        target=batch.target,
        filename=batch.filename,
        status=batch.status,
        error=batch.error,
        stats=batch.stats or {},
        pending_review=pending,
        created_at=batch.created_at,
    )


@router.post("", response_model=BatchOut, status_code=201)
async def create_import(
    request: Request,
    service: str = Form(),
    target: str | None = Form(default=None),
    file: UploadFile | None = None,
    payload: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BatchOut:
    if service not in PARSERS:
        raise HTTPException(status_code=422, detail="unknown import service")
    resolved_target = target or DEFAULT_TARGET[service]
    if resolved_target not in ("history", "watchlist"):
        raise HTTPException(status_code=422, detail="target must be history or watchlist")

    if file is not None:
        raw = await file.read(MAX_IMPORT_BYTES + 1)
        if len(raw) > MAX_IMPORT_BYTES:
            raise HTTPException(status_code=413, detail="file is larger than 10 MB")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="file must be UTF-8 text") from exc
        filename = file.filename
    elif payload:
        text = payload
        filename = None
    else:
        raise HTTPException(status_code=422, detail="provide a file or a pasted payload")

    try:
        rows = PARSERS[service](text)
    except parsers.ImportParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    batch = ImportBatch(
        user_id=user.id,
        service=service,
        target=resolved_target,
        filename=filename,
        status="pending",
        rows=list(rows),
        stats={"total": len(rows)},
        review_queue=[],
    )
    db.add(batch)
    await db.flush()
    await audit(
        db,
        "import.create",
        actor=user,
        request=request,
        object_type="import_batch",
        object_id=str(batch.id),
        detail={"service": service, "rows": len(rows)},
    )
    await db.commit()
    await queue.enqueue_process_batch(batch.id)
    return _batch_out(batch)


@router.get("", response_model=list[BatchOut])
async def list_imports(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[BatchOut]:
    batches = (
        (
            await db.execute(
                select(ImportBatch)
                .where(ImportBatch.user_id == user.id)
                .order_by(ImportBatch.created_at.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    return [_batch_out(b) for b in batches]


async def _get_batch(db: AsyncSession, batch_id: str, user: User) -> ImportBatch:
    try:
        bid = uuid.UUID(batch_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="import not found") from exc
    batch = (
        await db.execute(
            select(ImportBatch).where(ImportBatch.id == bid, ImportBatch.user_id == user.id)
        )
    ).scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=404, detail="import not found")
    return batch


class BatchDetail(BatchOut):
    review_queue: list


@router.get("/{batch_id}", response_model=BatchDetail)
async def import_detail(
    batch_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BatchDetail:
    batch = await _get_batch(db, batch_id, user)
    base = _batch_out(batch)
    return BatchDetail(
        **base.model_dump(),
        review_queue=[e for e in (batch.review_queue or []) if not e.get("resolved")],
    )


class ResolveBody(BaseModel):
    index: int = Field(ge=0)
    tmdb_id: int
    type: str = Field(pattern="^(movie|tv)$")


@router.post("/{batch_id}/resolve", response_model=BatchOut)
async def resolve_item(
    batch_id: str,
    body: ResolveBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BatchOut:
    batch = await _get_batch(db, batch_id, user)
    try:
        await import_service.resolve_review_item(
            db, batch, user, body.index, body.tmdb_id, body.type
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.commit()
    return _batch_out(batch)


class DismissBody(BaseModel):
    index: int = Field(ge=0)


@router.post("/{batch_id}/dismiss", response_model=BatchOut)
async def dismiss_item(
    batch_id: str,
    body: DismissBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BatchOut:
    batch = await _get_batch(db, batch_id, user)
    try:
        await import_service.dismiss_review_item(db, batch, body.index)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.commit()
    return _batch_out(batch)
