import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import budget, crypto, embeddings, nlsearch, taste
from app.ai import client as ai_client
from app.audit import audit
from app.auth.deps import csrf_protect, get_current_user, require_admin
from app.config import get_settings
from app.db import get_db
from app.models import Title, TitleEmbedding, User
from app.routers.catalog import TitleCard, _card_from_title

router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])


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


class AIStatus(BaseModel):
    enabled: bool
    embedded_titles: int


@router.get("/ai/status", response_model=AIStatus)
async def ai_status(db: AsyncSession = Depends(get_db)) -> AIStatus:
    """Whether the assistant is on, and how much of the catalog it knows.

    Deliberately does not name the model. Which model answers is an operator
    decision, it changes without notice, and putting it in front of people
    invites them to judge the answer by the label rather than the answer.
    Admins see it in Admin, AI settings, where it can also be changed.
    """
    settings = await ai_client.get_ai_settings(db)
    count = (await db.execute(select(func.count(TitleEmbedding.title_id)))).scalar_one()
    await db.commit()
    return AIStatus(enabled=settings.enabled, embedded_titles=count)


class NLSearchBody(BaseModel):
    q: str = Field(min_length=1, max_length=500)


class NLSearchResponse(BaseModel):
    parsed: dict
    results: list[TitleCard]


@router.post("/ai/search", response_model=NLSearchResponse)
async def ai_search(
    body: NLSearchBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _csrf: None = Depends(csrf_protect),
) -> NLSearchResponse:
    await budget.spend(user)
    try:
        outcome = await nlsearch.nl_search(db, user, body.q)
    except ai_client.AIDisabled as exc:
        raise HTTPException(status_code=503, detail="ai_disabled") from exc
    except ai_client.AIError as exc:
        raise HTTPException(status_code=502, detail="ai_unavailable") from exc
    await db.commit()
    return NLSearchResponse(
        parsed=outcome["parsed"],
        results=[_card(title) for title, _score in outcome["results"]],
    )


class SimilarResponse(BaseModel):
    results: list[TitleCard]


@router.get("/titles/{media_type}/{tmdb_id}/similar", response_model=SimilarResponse)
async def similar_titles(
    media_type: str,
    tmdb_id: int,
    db: AsyncSession = Depends(get_db),
) -> SimilarResponse:
    title = (
        await db.execute(select(Title).where(Title.tmdb_id == tmdb_id, Title.type == media_type))
    ).scalar_one_or_none()
    if title is None:
        return SimilarResponse(results=[])
    embedding = (
        await db.execute(select(TitleEmbedding).where(TitleEmbedding.title_id == title.id))
    ).scalar_one_or_none()
    if embedding is None:
        return SimilarResponse(results=[])
    try:
        import numpy as np

        ranked = await taste.rank_titles_by_vector(
            db, np.array(embedding.embedding), limit=12, exclude_title_ids={title.id}
        )
    except ai_client.AIDisabled:
        return SimilarResponse(results=[])
    await db.commit()
    return SimilarResponse(results=[_card(t) for t, _ in ranked])


class TagsResponse(BaseModel):
    tags: list[dict]


@router.get("/titles/{media_type}/{tmdb_id}/tags", response_model=TagsResponse)
async def title_tags(
    media_type: str, tmdb_id: int, db: AsyncSession = Depends(get_db)
) -> TagsResponse:
    title = (
        await db.execute(select(Title).where(Title.tmdb_id == tmdb_id, Title.type == media_type))
    ).scalar_one_or_none()
    if title is None:
        return TagsResponse(tags=[])
    return TagsResponse(tags=await embeddings.get_title_tags(db, title.id))


class ExplainBody(BaseModel):
    type: str = Field(pattern="^(movie|tv)$")
    tmdb_id: int


EXPLAIN_SYSTEM = """You write one short sentence explaining why a specific
film or series fits someone, given their recent favorites. Plain text, no
lists, no emojis, at most 30 words, warm but concrete."""


@router.post("/ai/explain")
async def explain_pick(
    body: ExplainBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _csrf: None = Depends(csrf_protect),
) -> dict:
    await budget.spend(user)
    title = (
        await db.execute(
            select(Title).where(Title.tmdb_id == body.tmdb_id, Title.type == body.type)
        )
    ).scalar_one_or_none()
    if title is None:
        raise HTTPException(status_code=404, detail="title not known yet")
    from app.models import WatchEvent

    favorites = (
        (
            await db.execute(
                select(Title.name)
                .join(WatchEvent, WatchEvent.title_id == Title.id)
                .where(
                    WatchEvent.user_id == user.id,
                    (WatchEvent.loved.is_(True)) | (WatchEvent.rating_10 >= 8),
                )
                .order_by(WatchEvent.watched_at.desc())
                .limit(8)
            )
        )
        .scalars()
        .all()
    )
    prompt = (
        f"Their recent favorites: {', '.join(favorites) if favorites else 'unknown'}.\n"
        f"The pick: {title.name} ({title.year}). Overview: {title.overview or 'n/a'}"
    )
    try:
        text = await ai_client.chat_text(db, EXPLAIN_SYSTEM, prompt, max_tokens=80)
    except ai_client.AIDisabled as exc:
        raise HTTPException(status_code=503, detail="ai_disabled") from exc
    except ai_client.AIError as exc:
        raise HTTPException(status_code=502, detail="ai_unavailable") from exc
    return {"explanation": text}


class AISettingsBody(BaseModel):
    enabled: bool
    base_url: str = Field(min_length=1, max_length=400)
    chat_model: str = Field(min_length=1, max_length=200)
    embed_model: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(default=None, max_length=400)


class AISettingsOut(BaseModel):
    enabled: bool
    base_url: str
    chat_model: str
    embed_model: str
    has_api_key: bool


admin_router = APIRouter(prefix="/api/admin/settings", dependencies=[Depends(require_admin)])


@admin_router.get("/ai", response_model=AISettingsOut)
async def get_ai_settings_admin(db: AsyncSession = Depends(get_db)) -> AISettingsOut:
    settings = await ai_client.get_ai_settings(db)
    await db.commit()
    return AISettingsOut(
        enabled=settings.enabled,
        base_url=settings.base_url,
        chat_model=settings.chat_model,
        embed_model=settings.embed_model,
        has_api_key=bool(settings.api_key_enc),
    )


@admin_router.put("/ai", response_model=AISettingsOut)
async def update_ai_settings(
    body: AISettingsBody,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    _csrf: None = Depends(csrf_protect),
) -> AISettingsOut:
    settings = await ai_client.get_ai_settings(db)
    settings.enabled = body.enabled
    settings.base_url = body.base_url.rstrip("/")
    settings.chat_model = body.chat_model
    settings.embed_model = body.embed_model
    if body.api_key is not None:
        settings.api_key_enc = crypto.encrypt(body.api_key) if body.api_key else None
    await audit(
        db,
        "settings.ai_update",
        actor=admin,
        request=request,
        detail={"enabled": body.enabled, "base_url": settings.base_url},
    )
    await db.commit()
    return AISettingsOut(
        enabled=settings.enabled,
        base_url=settings.base_url,
        chat_model=settings.chat_model,
        embed_model=settings.embed_model,
        has_api_key=bool(settings.api_key_enc),
    )


class ChatTurn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=4000)


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


class ChatResponse(BaseModel):
    reply: str
    results: list[TitleCard]


@router.post("/chat/stream", dependencies=[Depends(csrf_protect)])
async def chat_stream(
    body: ChatBody,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """The same answer as /api/chat, narrated as it happens.

    Server-sent events rather than one response at the end, so the interface
    can show what is actually going on: how many titles were searched, which
    ones are being considered, which model was asked, and how many of the
    titles it named survived being checked against the catalog. Every event
    is emitted after the work it describes, so nothing in the trace is a
    guess about the future."""
    await budget.spend(user)
    from app.ai import chat as chat_module

    async def events() -> AsyncIterator[str]:
        # The request-scoped session is closed before a streaming body runs
        # (FastAPI tears down yield-dependencies first), so the generator
        # owns its session for the whole answer. Same fault the home stream
        # had: it works under the test transport and hangs under uvicorn.
        from app.db import get_sessionmaker

        try:
            async with get_sessionmaker()() as db:
                async for step in chat_module.answer_steps(
                    db, user, body.message, [turn.model_dump() for turn in body.history]
                ):
                    if step.get("type") == "done":
                        payload = {
                            "type": "done",
                            "reply": step["reply"],
                            "results": [_card_from_title(t).model_dump() for t in step["titles"]],
                        }
                    else:
                        payload = step
                    yield f"data: {json.dumps(payload)}\n\n"
                await db.commit()
        except ai_client.AIDisabled:
            yield f"data: {json.dumps({'type': 'error', 'detail': 'ai_disabled'})}\n\n"
        except ai_client.AIError as exc:
            # The real reason, not a shrug. An empty reply from a free model
            # and a missing API key are different problems.
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # nginx buffers proxied responses by default, which would hold
            # every event back until the stream closed.
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(csrf_protect)])
async def chat(
    body: ChatBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """Talk to the assistant. It answers in words and in real title cards."""
    await budget.spend(user)
    from app.ai import chat as chat_module

    try:
        result = await chat_module.answer(
            db,
            user,
            body.message,
            [{"role": t.role, "content": t.content} for t in body.history],
        )
    except ai_client.AIDisabled as exc:
        raise HTTPException(status_code=503, detail="ai_disabled") from exc
    except ai_client.AIError as exc:
        raise HTTPException(status_code=502, detail="ai_unavailable") from exc

    await db.commit()
    return ChatResponse(
        reply=result["reply"],
        results=[_card_from_title(t) for t in result["titles"]],
    )


class AdvisoryItem(BaseModel):
    text: str
    spoiler: bool = False


class AdvisoryCategory(BaseModel):
    key: str
    label: str
    severity: str
    note: str
    # The itemised entries, present only when the guide came from IMDb.
    items: list[AdvisoryItem] = []
    total: int = 0


class AdvisoryResponse(BaseModel):
    categories: list[AdvisoryCategory]
    summary: str
    # Where this came from: "imdb" is what people wrote after watching,
    # "estimate" is inferred from the description and the age rating. The
    # interface must say which, because they are not the same claim.
    source: str = "estimate"
    # Kept for older clients; true whenever the source is the estimate.
    generated: bool = True


@router.get("/titles/{media_type}/{tmdb_id}/advisory", response_model=AdvisoryResponse)
async def content_advisory(
    media_type: str,
    tmdb_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdvisoryResponse:
    """What is actually in this one, category by category.

    IMDb's parents guide first: real entries written by people who watched
    it, with the severity they voted on. Only when there is no guide does
    this fall back to an estimate from the description and the official
    rating, and the response says which of the two it is."""
    from app.ai import advisories
    from app.catalog import imdb_guide, ingest

    if media_type not in ("movie", "tv"):
        raise HTTPException(status_code=404, detail="unknown media type")

    title = await ingest.ensure_title(db, media_type, tmdb_id)
    # Off unless the operator turned it on: see WD_IMDB_GUIDE_ENABLED.
    real = None
    if get_settings().imdb_guide_enabled:
        real = await imdb_guide.for_title(db, title)
    if real is not None:
        await db.commit()
        return AdvisoryResponse(**real, generated=False)

    try:
        result = await advisories.generate(db, title)
    except ai_client.AIDisabled as exc:
        raise HTTPException(status_code=503, detail="ai_disabled") from exc
    except ai_client.AIError as exc:
        raise HTTPException(status_code=502, detail="ai_unavailable") from exc
    await db.commit()
    return AdvisoryResponse(**result, source="estimate")
