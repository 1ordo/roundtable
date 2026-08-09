import contextlib
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import csrf_protect, get_current_user, require_admin
from app.db import get_db
from app.models import Group, Interaction, Title, User, WatchEvent
from app.routers.catalog import TitleCard, invalidate_home

router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])

VIEW_DEDUPE_HOURS = 6


class SignalBody(BaseModel):
    kind: str = Field(pattern="^(view|click_out|like|dislike)$")


class SignalState(BaseModel):
    liked: bool
    disliked: bool


async def _get_title(db: AsyncSession, media_type: str, tmdb_id: int) -> Title:
    title = (
        await db.execute(select(Title).where(Title.tmdb_id == tmdb_id, Title.type == media_type))
    ).scalar_one_or_none()
    if title is None:
        raise HTTPException(status_code=404, detail="title not known yet")
    return title


async def _signal_state(db: AsyncSession, user: User, title: Title) -> SignalState:
    kinds = set(
        (
            await db.execute(
                select(Interaction.kind).where(
                    Interaction.user_id == user.id,
                    Interaction.title_id == title.id,
                    Interaction.kind.in_(["like", "dislike"]),
                )
            )
        ).scalars()
    )
    return SignalState(liked="like" in kinds, disliked="dislike" in kinds)


@router.post(
    "/titles/{media_type}/{tmdb_id}/signal",
    response_model=SignalState,
    dependencies=[Depends(csrf_protect)],
)
async def record_signal(
    media_type: str,
    tmdb_id: int,
    body: SignalBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SignalState:
    title = await _get_title(db, media_type, tmdb_id)

    if body.kind == "view":
        recent = (
            await db.execute(
                select(Interaction.id).where(
                    Interaction.user_id == user.id,
                    Interaction.title_id == title.id,
                    Interaction.kind == "view",
                    Interaction.created_at > datetime.now(UTC) - timedelta(hours=VIEW_DEDUPE_HOURS),
                )
            )
        ).first()
        if recent is None:
            db.add(Interaction(user_id=user.id, title_id=title.id, kind="view"))
    elif body.kind == "click_out":
        db.add(Interaction(user_id=user.id, title_id=title.id, kind="click_out"))
    else:
        opposite = "dislike" if body.kind == "like" else "like"
        await db.execute(
            delete(Interaction).where(
                Interaction.user_id == user.id,
                Interaction.title_id == title.id,
                Interaction.kind == opposite,
            )
        )
        existing = (
            (
                await db.execute(
                    select(Interaction).where(
                        Interaction.user_id == user.id,
                        Interaction.title_id == title.id,
                        Interaction.kind == body.kind,
                    )
                )
            )
            .scalars()
            .first()
        )
        if existing is not None:
            # Second tap toggles the signal off.
            await db.execute(
                delete(Interaction).where(
                    Interaction.user_id == user.id,
                    Interaction.title_id == title.id,
                    Interaction.kind == body.kind,
                )
            )
        else:
            db.add(Interaction(user_id=user.id, title_id=title.id, kind=body.kind))

    if body.kind in ("like", "dislike"):
        # A deliberate verdict should change the recommendations now, not
        # once a few more views have gone by.
        from app.ai import client as ai_client
        from app.ai import taste as taste_module

        with contextlib.suppress(ai_client.AIDisabled, ai_client.AIError):
            await taste_module.invalidate_taste(db, user)

    await db.flush()
    state = await _signal_state(db, user, title)
    await db.commit()
    await invalidate_home(str(user.id))
    return state


@router.get("/titles/{media_type}/{tmdb_id}/signal", response_model=SignalState)
async def signal_state(
    media_type: str,
    tmdb_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SignalState:
    try:
        title = await _get_title(db, media_type, tmdb_id)
    except HTTPException:
        return SignalState(liked=False, disliked=False)
    return await _signal_state(db, user, title)


class GroupBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    member_usernames: list[str] = Field(min_length=1, max_length=12)


class GroupOut(BaseModel):
    id: str
    name: str
    members: list[str]
    created_by: str


def _group_out(group: Group, usernames: dict[uuid.UUID, str]) -> GroupOut:
    return GroupOut(
        id=str(group.id),
        name=group.name,
        members=[usernames.get(uuid.UUID(mid), "unknown") for mid in (group.member_ids or [])],
        created_by=usernames.get(group.created_by, "unknown"),
    )


async def _usernames(db: AsyncSession) -> dict[uuid.UUID, str]:
    rows = (await db.execute(select(User.id, User.username))).all()
    return {row[0]: row[1] for row in rows}


@router.get("/groups", response_model=list[GroupOut])
async def list_groups(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[GroupOut]:
    groups = (
        (
            await db.execute(
                select(Group).where(Group.tenant_id == user.tenant_id).order_by(Group.created_at)
            )
        )
        .scalars()
        .all()
    )
    names = await _usernames(db)
    mine = [g for g in groups if str(user.id) in (g.member_ids or []) or g.created_by == user.id]
    return [_group_out(g, names) for g in mine]


@router.post(
    "/groups", response_model=GroupOut, status_code=201, dependencies=[Depends(csrf_protect)]
)
async def create_group(
    body: GroupBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GroupOut:
    wanted = {name.strip().lower() for name in body.member_usernames}
    wanted.add(user.username.lower())
    users = (
        (
            await db.execute(
                select(User).where(
                    func.lower(User.username).in_(wanted), User.tenant_id == user.tenant_id
                )
            )
        )
        .scalars()
        .all()
    )
    found = {u.username.lower() for u in users}
    missing = wanted - found
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"no account for: {', '.join(sorted(missing))}. "
            "Ask your admin to pre-create them.",
        )
    group = Group(
        tenant_id=user.tenant_id,
        created_by=user.id,
        name=body.name.strip(),
        member_ids=[str(u.id) for u in users],
    )
    db.add(group)
    await db.flush()
    names = await _usernames(db)
    await db.commit()
    return _group_out(group, names)


@router.delete("/groups/{group_id}", status_code=204, dependencies=[Depends(csrf_protect)])
async def delete_group(
    group_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        gid = uuid.UUID(group_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="group not found") from exc
    group = (await db.execute(select(Group).where(Group.id == gid))).scalar_one_or_none()
    if group is None or group.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="group not found")
    if group.created_by != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="only the creator can delete a group")
    await db.delete(group)
    await db.commit()


class GroupSuggestBody(BaseModel):
    # Optional per-username weight, 0.1 to 3. Missing members default to 1.
    weights: dict[str, float] | None = None


class GroupSuggestions(BaseModel):
    results: list[TitleCard]
    without_taste: list[str]


@router.post("/groups/{group_id}/suggestions", response_model=GroupSuggestions)
async def group_suggestions(
    group_id: str,
    body: GroupSuggestBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _csrf: None = Depends(csrf_protect),
) -> GroupSuggestions:
    from app.ai import client as ai_client
    from app.ai import taste as taste_module

    try:
        gid = uuid.UUID(group_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="group not found") from exc
    group = (await db.execute(select(Group).where(Group.id == gid))).scalar_one_or_none()
    if group is None or group.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="group not found")

    member_ids = [uuid.UUID(mid) for mid in (group.member_ids or [])]
    members = (await db.execute(select(User).where(User.id.in_(member_ids)))).scalars().all()

    tastes = []
    weights = []
    without = []
    exclude: set[uuid.UUID] = set()
    languages: list[str] = []
    try:
        for member in members:
            vector = await taste_module.get_taste(db, member)
            if vector is None:
                without.append(member.username)
                continue
            tastes.append(vector)
            weights.append((body.weights or {}).get(member.username, 1.0))
            exclude |= await taste_module.watched_title_ids(db, member)
            languages.extend((member.prefs or {}).get("languages", []))
        if not tastes:
            return GroupSuggestions(results=[], without_taste=without)
        blended = taste_module.blend_tastes(tastes, weights)
        ranked = await taste_module.diversified_ranking(
            db, blended, limit=24, exclude_title_ids=exclude, languages=languages or None
        )
    except ai_client.AIDisabled as exc:
        raise HTTPException(status_code=503, detail="ai_disabled") from exc
    await db.commit()
    return GroupSuggestions(
        results=[
            TitleCard(
                tmdb_id=t.tmdb_id,
                type=t.type,
                name=t.name,
                poster_path=t.poster_path,
                backdrop_path=t.backdrop_path,
                year=t.year,
                tmdb_rating=t.tmdb_rating,
            )
            for t, _ in ranked
            if t.poster_path
        ],
        without_taste=without,
    )


class ActivityResponse(BaseModel):
    by_kind_30d: dict[str, int]
    per_user: list[dict]
    top_viewed: list[dict]
    top_liked: list[dict]


admin_router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])


@admin_router.get("/activity", response_model=ActivityResponse)
async def activity(db: AsyncSession = Depends(get_db)) -> ActivityResponse:
    since = datetime.now(UTC) - timedelta(days=30)

    kind_rows = (
        await db.execute(
            select(Interaction.kind, func.count(Interaction.id))
            .where(Interaction.created_at >= since)
            .group_by(Interaction.kind)
        )
    ).all()
    by_kind: dict[str, int] = {row[0]: row[1] for row in kind_rows}
    watches = (
        await db.execute(select(func.count(WatchEvent.id)).where(WatchEvent.created_at >= since))
    ).scalar_one()
    by_kind["watched"] = watches

    per_user_rows = (
        await db.execute(
            select(User.username, Interaction.kind, func.count(Interaction.id))
            .join(Interaction, Interaction.user_id == User.id)
            .where(Interaction.created_at >= since)
            .group_by(User.username, Interaction.kind)
        )
    ).all()
    per_user: dict[str, dict] = {}
    for username, kind, count in per_user_rows:
        per_user.setdefault(username, {"username": username})[kind] = count

    async def top_titles(kind: str) -> list[dict]:
        rows = (
            await db.execute(
                select(Title.name, func.count(Interaction.id).label("n"))
                .join(Interaction, Interaction.title_id == Title.id)
                .where(Interaction.kind == kind, Interaction.created_at >= since)
                .group_by(Title.name)
                .order_by(func.count(Interaction.id).desc())
                .limit(10)
            )
        ).all()
        return [{"name": name, "count": count} for name, count in rows]

    return ActivityResponse(
        by_kind_30d=by_kind,
        per_user=list(per_user.values()),
        top_viewed=await top_titles("view"),
        top_liked=await top_titles("like"),
    )


class PersonOut(BaseModel):
    username: str
    avatar_path: str | None
    is_me: bool


@router.get("/people", response_model=list[PersonOut])
async def people(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[PersonOut]:
    """Everyone you can invite to a watch night."""
    rows = (
        (
            await db.execute(
                select(User)
                .where(User.tenant_id == user.tenant_id, User.is_active.is_(True))
                .order_by(User.username)
            )
        )
        .scalars()
        .all()
    )
    return [
        PersonOut(username=p.username, avatar_path=p.avatar_path, is_me=p.id == user.id)
        for p in rows
    ]
