"""Comments on titles, and the feed of what your friends have written.

Two rules shape this:

  visibility is the author's   a comment is visible to exactly whoever can
                               see its author's profile, so switching to
                               private takes everything you wrote with it.
  a comment is a signal        writing about something is a stronger
                               statement of interest than clicking it, so it
                               feeds the taste vector like any other action.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.audit import audit
from app.auth.deps import csrf_protect, get_current_user
from app.db import get_db
from app.models import Comment, CommentLike, Title, User
from app.social import visibility

router = APIRouter(prefix="/api")

MAX_BODY = 2000
# How long someone gets to fix a typo before the edit is marked.
QUIET_EDIT = 300


class CommentAuthor(BaseModel):
    handle: str | None
    display_name: str | None
    username: str
    avatar_path: str | None


class CommentOut(BaseModel):
    id: str
    body: str
    spoiler: bool
    created_at: datetime
    edited_at: datetime | None
    author: CommentAuthor
    likes: int
    you_liked: bool
    yours: bool
    # Present on the feed, absent on a title page where it would be noise.
    title: dict | None = None
    # The post this one is sharing, if any. One level only: a share of a
    # share points at the original, so the chain never nests.
    shared: "CommentOut | None" = None
    # Replies to this post, and how many there are.
    replies: list["CommentOut"] = []
    reply_count: int = 0


class CommentsPage(BaseModel):
    total: int
    comments: list[CommentOut]


class WriteComment(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_BODY)
    spoiler: bool = False


class WritePost(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_BODY)
    spoiler: bool = False
    # Optional: a post can stand alone, name a title, or share another post.
    type: str | None = None
    tmdb_id: int | None = None
    shares: str | None = None
    # Replying to a post rather than posting about a film. A reply from the
    # feed is about what someone said, not about the film they mentioned.
    reply_to: str | None = None


# Everything _out touches, so it never lazy loads. A post read without
# these blows up on reshares only, which is the worst kind of bug: it looks
# like it works.
def _loaded():
    return (
        joinedload(Comment.user),
        joinedload(Comment.title),
        joinedload(Comment.shared).joinedload(Comment.user),
        joinedload(Comment.shared).joinedload(Comment.title),
    )


def _author(user: User) -> CommentAuthor:
    return CommentAuthor(
        handle=user.handle,
        display_name=user.display_name,
        username=user.username,
        avatar_path=user.avatar_path,
    )


def _out(
    comment: Comment,
    viewer: User,
    likes: dict[uuid.UUID, int],
    liked: set[uuid.UUID],
    allowed: set[uuid.UUID],
    with_title: bool = False,
    replies: list[Comment] | None = None,
) -> CommentOut:
    """Serialise one post.

    `allowed` is not optional on purpose. A reshare carries someone else's
    post inside it, and the resharer's own audience is not the original
    author's audience: A may reshare B's friends-only post to C, who is not
    B's friend. The embedded original is dropped when its author is not in
    the set, leaving the resharer's own words, which are theirs to share.
    """
    shared = comment.shared
    if shared is not None and shared.user_id not in allowed:
        shared = None
    return CommentOut(
        id=str(comment.id),
        body=comment.body,
        spoiler=comment.spoiler,
        created_at=comment.created_at,
        edited_at=comment.edited_at,
        author=_author(comment.user),
        likes=likes.get(comment.id, 0),
        you_liked=comment.id in liked,
        yours=comment.user_id == viewer.id,
        title=(
            {
                "tmdb_id": comment.title.tmdb_id,
                "type": comment.title.type,
                "name": comment.title.name,
                "poster_path": comment.title.poster_path,
                "year": comment.title.year,
            }
            if with_title and comment.title is not None
            else None
        ),
        shared=(
            _out(shared, viewer, likes, liked, allowed, with_title=True)
            if shared is not None
            else None
        ),
        replies=[_out(r, viewer, likes, liked, allowed) for r in replies or []],
        reply_count=len(replies or []),
    )


async def _like_state(
    db: AsyncSession, viewer: User, ids: list[uuid.UUID]
) -> tuple[dict[uuid.UUID, int], set[uuid.UUID]]:
    """Counts and whether the viewer liked each, in two queries rather than
    two per comment."""
    if not ids:
        return {}, set()
    count_rows = (
        await db.execute(
            select(CommentLike.comment_id, func.count(CommentLike.id))
            .where(CommentLike.comment_id.in_(ids))
            .group_by(CommentLike.comment_id)
        )
    ).all()
    counts: dict[uuid.UUID, int] = {row[0]: row[1] for row in count_rows}
    mine = set(
        (
            await db.execute(
                select(CommentLike.comment_id).where(
                    CommentLike.comment_id.in_(ids), CommentLike.user_id == viewer.id
                )
            )
        )
        .scalars()
        .all()
    )
    return counts, mine


async def _replies_for(
    db: AsyncSession, viewer: User, parents: list[Comment], allowed: set
) -> dict[uuid.UUID, list[Comment]]:
    """Every reply to a page of posts, in one query."""
    ids = [p.id for p in parents]
    if not ids:
        return {}
    rows = (
        (
            await db.execute(
                select(Comment)
                .options(joinedload(Comment.user), joinedload(Comment.title))
                .where(Comment.reply_to_id.in_(ids), Comment.user_id.in_(allowed))
                .order_by(Comment.created_at)
            )
        )
        .scalars()
        .all()
    )
    out: dict[uuid.UUID, list[Comment]] = {}
    for row in rows:
        if row.reply_to_id is not None:
            out.setdefault(row.reply_to_id, []).append(row)
    return out


async def _title_or_404(db: AsyncSession, media_type: str, tmdb_id: int) -> Title:
    from app.catalog import ingest

    if media_type not in ("movie", "tv"):
        raise HTTPException(status_code=404, detail="unknown media type")
    title = await ingest.ensure_title(db, media_type, tmdb_id)
    if title is None:
        raise HTTPException(status_code=404, detail="title not found")
    return title


@router.get("/titles/{media_type}/{tmdb_id}/comments", response_model=CommentsPage)
async def list_comments(
    media_type: str,
    tmdb_id: int,
    viewer: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
) -> CommentsPage:
    """What people you can see have said about this one."""
    title = await _title_or_404(db, media_type, tmdb_id)
    allowed = await visibility.visible_user_ids_for_panel(db, viewer, "posts")

    base = select(Comment).where(
        Comment.title_id == title.id,
        Comment.user_id.in_(allowed),
        Comment.reply_to_id.is_(None),
    )
    total = (
        await db.execute(
            select(func.count(Comment.id)).where(
                Comment.title_id == title.id,
                Comment.user_id.in_(allowed),
                Comment.reply_to_id.is_(None),
            )
        )
    ).scalar_one()
    rows = (
        (
            await db.execute(
                base.options(*_loaded())
                .order_by(Comment.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    replies = await _replies_for(db, viewer, list(rows), allowed)
    every = [c.id for c in rows] + [r.id for group in replies.values() for r in group]
    counts, liked = await _like_state(db, viewer, every)
    await db.commit()
    return CommentsPage(
        total=total,
        comments=[_out(c, viewer, counts, liked, allowed, replies=replies.get(c.id)) for c in rows],
    )


@router.post(
    "/titles/{media_type}/{tmdb_id}/comments",
    response_model=CommentOut,
    status_code=201,
    dependencies=[Depends(csrf_protect)],
)
async def write_comment(
    media_type: str,
    tmdb_id: int,
    body: WriteComment,
    request: Request,
    viewer: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommentOut:
    text = body.body.strip()
    if not text:
        raise HTTPException(status_code=422, detail="say something")

    title = await _title_or_404(db, media_type, tmdb_id)
    comment = Comment(user_id=viewer.id, title_id=title.id, body=text, spoiler=body.spoiler)
    db.add(comment)
    await db.flush()

    # Writing about something is a stronger statement than clicking it, so
    # it counts toward the taste vector like any other action.
    from app.ai import taste as taste_module
    from app.models import Interaction

    # The strength lives in taste.INTERACTION_WEIGHTS, keyed by kind, so
    # every signal is weighted in one place rather than at each call site.
    db.add(Interaction(user_id=viewer.id, title_id=title.id, kind="comment"))
    await taste_module.invalidate_taste(db, viewer)

    await audit(
        db,
        "comment.create",
        actor=viewer,
        request=request,
        object_type="title",
        object_id=str(title.tmdb_id),
    )
    await db.commit()
    loaded = (
        await db.execute(select(Comment).options(*_loaded()).where(Comment.id == comment.id))
    ).scalar_one()
    allowed = await visibility.visible_user_ids_for_panel(db, viewer, "posts")
    return _out(loaded, viewer, {}, set(), allowed)


async def _own_comment(db: AsyncSession, comment_id: str, viewer: User) -> Comment:
    try:
        cid = uuid.UUID(comment_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="not found") from exc
    comment = (
        await db.execute(select(Comment).options(*_loaded()).where(Comment.id == cid))
    ).scalar_one_or_none()
    if comment is None:
        raise HTTPException(status_code=404, detail="not found")
    if comment.user_id != viewer.id:
        # Not "forbidden": whether a comment exists is itself something the
        # viewer may not be entitled to know.
        raise HTTPException(status_code=404, detail="not found")
    return comment


@router.patch(
    "/comments/{comment_id}", response_model=CommentOut, dependencies=[Depends(csrf_protect)]
)
async def edit_comment(
    comment_id: str,
    body: WriteComment,
    viewer: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommentOut:
    comment = await _own_comment(db, comment_id, viewer)
    text = body.body.strip()
    if not text:
        raise HTTPException(status_code=422, detail="say something")
    comment.body = text
    comment.spoiler = body.spoiler
    # A typo fixed in the first few minutes is not an edit worth flagging;
    # rewriting something an hour later is.
    created = comment.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    if (datetime.now(UTC) - created).total_seconds() > QUIET_EDIT:
        comment.edited_at = datetime.now(UTC)
    counts, liked = await _like_state(db, viewer, [comment.id])
    allowed = await visibility.visible_user_ids_for_panel(db, viewer, "posts")
    out = _out(comment, viewer, counts, liked, allowed, with_title=True)
    await db.commit()
    return out


@router.delete("/comments/{comment_id}", status_code=204, dependencies=[Depends(csrf_protect)])
async def delete_comment(
    comment_id: str,
    request: Request,
    viewer: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    comment = await _own_comment(db, comment_id, viewer)
    await db.execute(delete(Comment).where(Comment.id == comment.id))
    await audit(db, "comment.delete", actor=viewer, request=request)
    await db.commit()


@router.post(
    "/comments/{comment_id}/like", response_model=CommentOut, dependencies=[Depends(csrf_protect)]
)
async def toggle_like(
    comment_id: str,
    viewer: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommentOut:
    try:
        cid = uuid.UUID(comment_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="not found") from exc
    comment = (
        await db.execute(select(Comment).options(*_loaded()).where(Comment.id == cid))
    ).scalar_one_or_none()
    if comment is None:
        raise HTTPException(status_code=404, detail="not found")
    # You can only like what you were allowed to read.
    allowed = await visibility.visible_user_ids_for_panel(db, viewer, "posts")
    if comment.user_id not in allowed:
        raise HTTPException(status_code=404, detail="not found")

    existing = (
        await db.execute(
            select(CommentLike).where(
                CommentLike.comment_id == cid, CommentLike.user_id == viewer.id
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(CommentLike(comment_id=cid, user_id=viewer.id))
        from app.social import mentions

        await mentions.tell(db, viewer, comment.user_id, "liked your post", comment.body)
    else:
        await db.execute(delete(CommentLike).where(CommentLike.id == existing.id))
    await db.flush()
    counts, liked = await _like_state(db, viewer, [cid])
    out = _out(comment, viewer, counts, liked, allowed, with_title=True)
    await db.commit()
    return out


@router.post(
    "/posts", response_model=CommentOut, status_code=201, dependencies=[Depends(csrf_protect)]
)
async def write_post(
    body: WritePost,
    request: Request,
    viewer: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommentOut:
    """A post, with or without a title, with or without sharing another.

    Same table as a comment on a title, because they are the same thing: a
    comment is a post that names something."""
    text = body.body.strip()
    if not text:
        raise HTTPException(status_code=422, detail="say something")

    title = None
    if body.type and body.tmdb_id:
        title = await _title_or_404(db, body.type, body.tmdb_id)

    allowed = await visibility.visible_user_ids_for_panel(db, viewer, "posts")

    parent = None
    if body.reply_to:
        try:
            parent_id = uuid.UUID(body.reply_to)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="not found") from exc
        parent = (
            await db.execute(select(Comment).where(Comment.id == parent_id))
        ).scalar_one_or_none()
        if parent is None:
            raise HTTPException(status_code=404, detail="not found")
        if parent.user_id not in allowed:
            raise HTTPException(status_code=404, detail="not found")
        # A reply to a reply belongs to the same post, so threads stay one
        # level deep and a conversation is readable.
        if parent.reply_to_id is not None:
            parent = (
                await db.execute(select(Comment).where(Comment.id == parent.reply_to_id))
            ).scalar_one_or_none()
            if parent is None:
                raise HTTPException(status_code=404, detail="not found")

    shared_id = None
    if body.shares:
        try:
            original_id = uuid.UUID(body.shares)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="not found") from exc
        original = (
            await db.execute(select(Comment).where(Comment.id == original_id))
        ).scalar_one_or_none()
        if original is None:
            raise HTTPException(status_code=404, detail="not found")
        # You can only share what you were allowed to read.
        if original.user_id not in allowed:
            raise HTTPException(status_code=404, detail="not found")
        # Sharing a share points at the original, so the chain stays flat
        # and one deletion cannot orphan a stack of them.
        shared_id = original.shared_id or original.id
        if title is None and original.title_id is not None:
            title = (
                await db.execute(select(Title).where(Title.id == original.title_id))
            ).scalar_one_or_none()

    post = Comment(
        user_id=viewer.id,
        title_id=title.id if title else None,
        body=text,
        spoiler=body.spoiler,
        shared_id=shared_id,
        reply_to_id=parent.id if parent else None,
    )
    db.add(post)
    await db.flush()

    # Tell whoever wrote the thing you replied to or shared.
    from app.social import mentions

    if parent is not None:
        await mentions.tell(db, viewer, parent.user_id, "replied to your post", text)
    elif shared_id is not None:
        original = (
            await db.execute(select(Comment).where(Comment.id == shared_id))
        ).scalar_one_or_none()
        if original is not None:
            await mentions.tell(db, viewer, original.user_id, "shared your post", text)

    if title is not None:
        from app.ai import taste as taste_module
        from app.models import Interaction

        db.add(Interaction(user_id=viewer.id, title_id=title.id, kind="comment"))
        await taste_module.invalidate_taste(db, viewer)

    await audit(db, "post.create", actor=viewer, request=request)
    await db.commit()
    loaded = (
        await db.execute(select(Comment).options(*_loaded()).where(Comment.id == post.id))
    ).scalar_one()
    return _out(loaded, viewer, {}, set(), allowed, with_title=True)


@router.get("/feed", response_model=CommentsPage)
async def feed(
    viewer: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(30, le=100),
    offset: int = Query(0, ge=0),
) -> CommentsPage:
    """Everything the people you can see have written lately."""
    allowed = await visibility.visible_user_ids_for_panel(db, viewer, "posts")
    total = (
        await db.execute(select(func.count(Comment.id)).where(Comment.user_id.in_(allowed)))
    ).scalar_one()
    rows = (
        (
            await db.execute(
                select(Comment)
                .options(*_loaded())
                .where(Comment.user_id.in_(allowed), Comment.reply_to_id.is_(None))
                .order_by(Comment.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    replies = await _replies_for(db, viewer, list(rows), allowed)
    every = [c.id for c in rows] + [r.id for group in replies.values() for r in group]
    counts, liked = await _like_state(db, viewer, every)
    await db.commit()
    return CommentsPage(
        total=total,
        comments=[
            _out(c, viewer, counts, liked, allowed, with_title=True, replies=replies.get(c.id))
            for c in rows
        ],
    )
