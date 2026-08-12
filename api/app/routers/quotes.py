"""Lines from films, picked or written.

Where they come from: the catalog carries no quote field, so there are two
honest options. Either the assistant proposes lines it recognises from a
film it knows, clearly labelled as suggestions to pick from, or someone
types the line they remember. Both end up in the same table with `source`
saying which, so a machine-proposed line is never passed off as a citation.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.audit import audit
from app.auth.deps import csrf_protect, get_current_user
from app.db import get_db
from app.models import Quote, QuoteLike, Title, User
from app.social import visibility

router = APIRouter(prefix="/api")

MAX_BODY = 600

SYSTEM = """You recall lines of dialogue from films and television.

Given a title, return the lines people actually quote from it: the ones
that get repeated, printed on posters, and used as captions.

Rules:
- Only lines you are confident are really from this title. Fewer correct
  lines is better than more invented ones.
- Give the character who says it. If you are not sure who says it, leave
  the character empty rather than guessing.
- No stage directions, no summaries, no lines you have reconstructed from
  the plot.
- If you do not know this title well, return an empty list. That is a
  perfectly good answer.

Reply as JSON: {"quotes": [{"text": "...", "character": "..."}]}"""


class QuoteOut(BaseModel):
    id: str
    body: str
    character: str | None
    source: str
    added_by: str | None
    likes: int
    you_liked: bool
    yours: bool


class QuotesPage(BaseModel):
    quotes: list[QuoteOut]


class Suggestion(BaseModel):
    text: str
    character: str | None = None


class SuggestionsOut(BaseModel):
    suggestions: list[Suggestion]
    # Said out loud, because the difference matters: these are recalled by a
    # language model, not read off a transcript.
    note: str = "Recalled by the assistant, so check anything that looks off."


class WriteQuote(BaseModel):
    body: str = Field(min_length=2, max_length=MAX_BODY)
    character: str | None = Field(default=None, max_length=120)


async def _title(db: AsyncSession, media_type: str, tmdb_id: int) -> Title:
    from app.catalog import ingest

    if media_type not in ("movie", "tv"):
        raise HTTPException(status_code=404, detail="unknown media type")
    title = await ingest.ensure_title(db, media_type, tmdb_id)
    if title is None:
        raise HTTPException(status_code=404, detail="title not found")
    return title


def _out(quote: Quote, viewer: User, likes: dict, liked: set) -> QuoteOut:
    author = quote.user
    return QuoteOut(
        id=str(quote.id),
        body=quote.body,
        character=quote.character,
        source=quote.source,
        added_by=((author.display_name or author.handle or author.username) if author else None),
        likes=likes.get(quote.id, 0),
        you_liked=quote.id in liked,
        yours=quote.user_id == viewer.id,
    )


async def _likes(db: AsyncSession, viewer: User, ids: list[uuid.UUID]) -> tuple[dict, set]:
    if not ids:
        return {}, set()
    rows = (
        await db.execute(
            select(QuoteLike.quote_id, func.count(QuoteLike.id))
            .where(QuoteLike.quote_id.in_(ids))
            .group_by(QuoteLike.quote_id)
        )
    ).all()
    counts: dict[uuid.UUID, int] = {row[0]: row[1] for row in rows}
    mine = set(
        (
            await db.execute(
                select(QuoteLike.quote_id).where(
                    QuoteLike.quote_id.in_(ids), QuoteLike.user_id == viewer.id
                )
            )
        )
        .scalars()
        .all()
    )
    return counts, mine


@router.get("/titles/{media_type}/{tmdb_id}/quotes", response_model=QuotesPage)
async def list_quotes(
    media_type: str,
    tmdb_id: int,
    viewer: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuotesPage:
    """Every line saved against this title that you are allowed to see.

    A quote carries its author's name, so it is a written thing and belongs
    to the "posts" panel, the same as a comment. Filtering here rather than
    in the template is what keeps a private account private on a page it
    does not own.
    """
    title = await _title(db, media_type, tmdb_id)
    allowed = await visibility.visible_user_ids_for_panel(db, viewer, "posts")
    rows = (
        (
            await db.execute(
                select(Quote)
                .options(joinedload(Quote.user))
                .where(
                    Quote.title_id == title.id,
                    # A catalog quote has no author, so there is nobody to
                    # keep it from. Only lines somebody typed carry a name.
                    or_(Quote.user_id.is_(None), Quote.user_id.in_(allowed)),
                )
                .order_by(Quote.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    counts, liked = await _likes(db, viewer, [q.id for q in rows])
    await db.commit()
    quotes = [_out(q, viewer, counts, liked) for q in rows]
    quotes.sort(key=lambda q: -q.likes)
    return QuotesPage(quotes=quotes)


@router.get("/titles/{media_type}/{tmdb_id}/quotes/suggestions", response_model=SuggestionsOut)
async def suggest_quotes(
    media_type: str,
    tmdb_id: int,
    viewer: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SuggestionsOut:
    """Lines to pick from, rather than a blank box.

    Cached on the title, because the answer for a given film does not
    change and every call costs a request."""
    from app.ai import client as ai_client
    from app.catalog import cache

    title = await _title(db, media_type, tmdb_id)
    key = f"quotes:{title.type}:{title.tmdb_id}"
    cached = await cache.cache_get(db, key, 24 * 90)
    if cached is not None:
        await db.commit()
        return SuggestionsOut(suggestions=[Suggestion(**s) for s in cached.get("quotes", [])])

    year = f" ({title.year})" if title.year else ""
    prompt = f"Title: {title.name}{year}\nType: {'series' if title.type == 'tv' else 'film'}"
    try:
        payload = await ai_client.chat_json(db, SYSTEM, prompt, max_tokens=700)
    except ai_client.AIDisabled as exc:
        raise HTTPException(status_code=503, detail="ai_disabled") from exc
    except ai_client.AIError as exc:
        raise HTTPException(status_code=502, detail="ai_unavailable") from exc

    out: list[Suggestion] = []
    for item in (payload.get("quotes") or [])[:12]:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip().strip('"')
        if len(text) < 2 or len(text) > MAX_BODY:
            continue
        character = str(item.get("character") or "").strip()[:120] or None
        out.append(Suggestion(text=text, character=character))

    await cache.cache_put(db, key, {"quotes": [s.model_dump() for s in out]})
    await db.commit()
    return SuggestionsOut(suggestions=out)


@router.post(
    "/titles/{media_type}/{tmdb_id}/quotes",
    response_model=QuoteOut,
    status_code=201,
    dependencies=[Depends(csrf_protect)],
)
async def add_quote(
    media_type: str,
    tmdb_id: int,
    body: WriteQuote,
    request: Request,
    viewer: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuoteOut:
    """Save a line, whether picked from the suggestions or typed."""
    title = await _title(db, media_type, tmdb_id)
    text = body.body.strip().strip('"')
    if not text:
        raise HTTPException(status_code=422, detail="type the line")

    existing = (
        (
            await db.execute(
                select(Quote).where(
                    Quote.title_id == title.id, func.lower(Quote.body) == text.lower()
                )
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        # Already saved by someone. Count it as a like rather than a
        # duplicate, which is what the person meant anyway.
        already = (
            await db.execute(
                select(QuoteLike).where(
                    QuoteLike.quote_id == existing.id, QuoteLike.user_id == viewer.id
                )
            )
        ).scalar_one_or_none()
        if already is None:
            db.add(QuoteLike(quote_id=existing.id, user_id=viewer.id))
            await db.flush()
        counts, liked = await _likes(db, viewer, [existing.id])
        await db.commit()
        await db.refresh(existing, ["user"])
        return _out(existing, viewer, counts, liked)

    quote = Quote(
        title_id=title.id,
        user_id=viewer.id,
        body=text,
        character=(body.character or "").strip() or None,
        source="user",
    )
    db.add(quote)
    await audit(
        db,
        "quote.add",
        actor=viewer,
        request=request,
        object_type="title",
        object_id=str(title.tmdb_id),
    )
    await db.commit()
    await db.refresh(quote, ["user"])
    return _out(quote, viewer, {}, set())


@router.post(
    "/quotes/{quote_id}/like", response_model=QuoteOut, dependencies=[Depends(csrf_protect)]
)
async def like_quote(
    quote_id: str,
    viewer: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuoteOut:
    try:
        qid = uuid.UUID(quote_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="not found") from exc
    quote = (
        await db.execute(select(Quote).options(joinedload(Quote.user)).where(Quote.id == qid))
    ).scalar_one_or_none()
    if quote is None:
        raise HTTPException(status_code=404, detail="not found")
    # You can only like what you were allowed to read, and the response
    # carries the quote itself, so an unchecked like is also a read.
    if quote.user_id not in await visibility.visible_user_ids_for_panel(db, viewer, "posts"):
        raise HTTPException(status_code=404, detail="not found")

    existing = (
        await db.execute(
            select(QuoteLike).where(QuoteLike.quote_id == qid, QuoteLike.user_id == viewer.id)
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(QuoteLike(quote_id=qid, user_id=viewer.id))
    else:
        await db.execute(delete(QuoteLike).where(QuoteLike.id == existing.id))
    await db.flush()
    counts, liked = await _likes(db, viewer, [qid])
    await db.commit()
    return _out(quote, viewer, counts, liked)


@router.delete("/quotes/{quote_id}", status_code=204, dependencies=[Depends(csrf_protect)])
async def remove_quote(
    quote_id: str,
    viewer: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        qid = uuid.UUID(quote_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="not found") from exc
    quote = (await db.execute(select(Quote).where(Quote.id == qid))).scalar_one_or_none()
    if quote is None or quote.user_id != viewer.id:
        raise HTTPException(status_code=404, detail="not found")
    await db.execute(delete(Quote).where(Quote.id == qid))
    await db.commit()


class FeaturedOut(BaseModel):
    featured_quote_id: str | None


@router.post(
    "/quotes/{quote_id}/feature",
    response_model=FeaturedOut,
    dependencies=[Depends(csrf_protect)],
)
async def feature_quote(
    quote_id: str,
    viewer: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FeaturedOut:
    """Put this line at the top of your profile, or take it down.

    Pressing the one already featured clears it, so the same control does
    both and there is no separate remove.

    Any line you can see may be featured, including one that came with the
    catalog: quoting somebody else's favourite line is the normal way people
    use a line, and it is attributed to the film either way.
    """
    try:
        qid = uuid.UUID(quote_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="not found") from exc

    if viewer.featured_quote_id == qid:
        viewer.featured_quote_id = None
        await db.commit()
        return FeaturedOut(featured_quote_id=None)

    quote = (await db.execute(select(Quote).where(Quote.id == qid))).scalar_one_or_none()
    if quote is None:
        raise HTTPException(status_code=404, detail="not found")
    # You can only feature a line you were allowed to read.
    if (
        quote.user_id is not None
        and quote.user_id not in await visibility.visible_user_ids_for_panel(db, viewer, "posts")
    ):
        raise HTTPException(status_code=404, detail="not found")

    viewer.featured_quote_id = qid
    await db.commit()
    return FeaturedOut(featured_quote_id=str(qid))
