"""Watch nights: a plan a group makes, not a list one person owns.

Two people or six. Nothing here assumes a pair: the queue, the votes and
the taste blend all take however many accepted the invitation.

The flow the endpoints implement, in order:

  1. someone hosts a night and invites friends
  2. each invitee accepts or declines; only people who accepted take part
  3. anyone taking part adds titles to a shared queue, and can vote for
     other people's picks. Suggestions are blended from everyone who is
     actually coming, not everyone who was asked.
  4. the night happens; the host marks what was watched. It lands in every
     participant's history at that moment, so nobody has to log it twice.
  5. after a delay the host chooses, everyone is asked what they thought.
     The answer updates their own watch event, so their taste learns from
     it exactly as if they had rated it themselves.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import csrf_protect, get_current_user
from app.db import get_db
from app.models import (
    NightMember,
    NightPick,
    NightVerdict,
    Title,
    User,
    WatchEvent,
    WatchNight,
)
from app.notifications import service as notifications
from app.routers.friends import friend_ids

router = APIRouter(prefix="/api")

MAX_QUEUE = 50


class NightPickOut(BaseModel):
    tmdb_id: int
    type: str
    name: str
    poster_path: str | None
    year: int | None
    suggested_by: str
    votes: int
    you_voted: bool


class NightMemberOut(BaseModel):
    username: str
    avatar_path: str | None
    status: str


class NightOut(BaseModel):
    id: str
    name: str
    host: str
    status: str
    scheduled_for: datetime | None
    survey_after_hours: int
    members: list[NightMemberOut]
    queue: list[NightPickOut]
    watched: NightPickOut | None = None
    watched_at: datetime | None = None
    # Your own place in it, so the interface knows which buttons to offer.
    your_status: str = "invited"
    you_host: bool = False
    # Set when it is time to say what you thought and you have not yet.
    awaiting_your_verdict: bool = False


async def _load(db: AsyncSession, night_id: str, user: User) -> WatchNight:
    try:
        nid = uuid.UUID(night_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="night not found") from exc
    night = (await db.execute(select(WatchNight).where(WatchNight.id == nid))).scalar_one_or_none()
    if night is None or night.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="night not found")
    member = (
        await db.execute(
            select(NightMember).where(
                NightMember.night_id == night.id, NightMember.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if member is None and night.host_id != user.id:
        # Not invited is indistinguishable from not existing, so a night
        # cannot be probed for by id.
        raise HTTPException(status_code=404, detail="night not found")
    return night


async def _serialize(db: AsyncSession, night: WatchNight, user: User) -> NightOut:
    members = (
        (await db.execute(select(NightMember).where(NightMember.night_id == night.id)))
        .scalars()
        .all()
    )
    people = {
        u.id: u
        for u in (
            await db.execute(
                select(User).where(User.id.in_([m.user_id for m in members] + [night.host_id]))
            )
        )
        .scalars()
        .all()
    }

    picks = (
        (await db.execute(select(NightPick).where(NightPick.night_id == night.id))).scalars().all()
    )
    title_ids = [p.title_id for p in picks]
    if night.watched_title_id:
        title_ids.append(night.watched_title_id)
    titles = {
        t.id: t
        for t in (await db.execute(select(Title).where(Title.id.in_(title_ids)))).scalars().all()
    }

    def pick_out(pick: NightPick) -> NightPickOut | None:
        title = titles.get(pick.title_id)
        if title is None:
            return None
        voters = pick.voter_ids or []
        return NightPickOut(
            tmdb_id=title.tmdb_id,
            type=title.type,
            name=title.name,
            poster_path=title.poster_path,
            year=title.year,
            suggested_by=(
                people[pick.suggested_by].username if pick.suggested_by in people else "someone"
            ),
            votes=len(voters),
            you_voted=str(user.id) in voters,
        )

    queue = [p for p in (pick_out(pick) for pick in picks) if p is not None]
    # Most wanted first, and a pick with no votes yet still shows up.
    queue.sort(key=lambda p: (-p.votes, p.name.lower()))

    watched = None
    if night.watched_title_id and night.watched_title_id in titles:
        title = titles[night.watched_title_id]
        watched = NightPickOut(
            tmdb_id=title.tmdb_id,
            type=title.type,
            name=title.name,
            poster_path=title.poster_path,
            year=title.year,
            suggested_by="",
            votes=0,
            you_voted=False,
        )

    mine = next((m for m in members if m.user_id == user.id), None)
    your_status = mine.status if mine else ("accepted" if night.host_id == user.id else "invited")

    awaiting = False
    if night.status == "watched" and your_status == "accepted":
        answered = (
            await db.execute(
                select(NightVerdict).where(
                    NightVerdict.night_id == night.id, NightVerdict.user_id == user.id
                )
            )
        ).scalar_one_or_none()
        awaiting = answered is None and _survey_due(night)

    return NightOut(
        id=str(night.id),
        name=night.name,
        host=people[night.host_id].username if night.host_id in people else "someone",
        status=night.status,
        scheduled_for=night.scheduled_for,
        survey_after_hours=night.survey_after_hours,
        members=[
            NightMemberOut(
                username=people[m.user_id].username if m.user_id in people else "someone",
                avatar_path=people[m.user_id].avatar_path if m.user_id in people else None,
                status=m.status,
            )
            for m in members
        ],
        queue=queue,
        watched=watched,
        watched_at=night.watched_at,
        your_status=your_status,
        you_host=night.host_id == user.id,
        awaiting_your_verdict=awaiting,
    )


def _survey_due(night: WatchNight) -> bool:
    """Whether enough time has passed to ask what someone thought."""
    if night.watched_at is None:
        return False
    watched_at = night.watched_at
    if watched_at.tzinfo is None:
        watched_at = watched_at.replace(tzinfo=UTC)
    return datetime.now(UTC) >= watched_at + timedelta(hours=night.survey_after_hours)


class NightBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    invite: list[str] = Field(default_factory=list)
    scheduled_for: datetime | None = None
    # Zero means ask as soon as it is marked watched.
    survey_after_hours: int = Field(default=12, ge=0, le=720)


@router.get("/nights", response_model=list[NightOut])
async def my_nights(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[NightOut]:
    mine = (
        (await db.execute(select(NightMember.night_id).where(NightMember.user_id == user.id)))
        .scalars()
        .all()
    )
    nights = (
        (
            await db.execute(
                select(WatchNight)
                .where(WatchNight.id.in_(mine) | (WatchNight.host_id == user.id))
                .order_by(WatchNight.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [await _serialize(db, night, user) for night in nights]


@router.post(
    "/nights", response_model=NightOut, status_code=201, dependencies=[Depends(csrf_protect)]
)
async def create_night(
    body: NightBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NightOut:
    """Invitations only go to friends. Being able to add anyone to anything
    is how a social feature turns into a way to bother people."""
    night = WatchNight(
        tenant_id=user.tenant_id,
        host_id=user.id,
        name=body.name.strip(),
        scheduled_for=body.scheduled_for,
        survey_after_hours=body.survey_after_hours,
    )
    db.add(night)
    await db.flush()
    # The host is in by definition; they proposed it.
    db.add(NightMember(night_id=night.id, user_id=user.id, status="accepted"))

    if body.invite:
        allowed = await friend_ids(db, user)
        wanted = {name.strip().lower() for name in body.invite}
        people = (
            (
                await db.execute(
                    select(User).where(User.tenant_id == user.tenant_id, User.is_active.is_(True))
                )
            )
            .scalars()
            .all()
        )
        by_name = {u.username.lower(): u for u in people}
        for name in wanted:
            other = by_name.get(name)
            if other is None or other.id == user.id:
                continue
            if other.id not in allowed:
                raise HTTPException(
                    status_code=403,
                    detail=f"you can only invite friends, and {other.username} is not one yet",
                )
            db.add(NightMember(night_id=night.id, user_id=other.id, status="invited"))
            await notifications.notify(
                db,
                other,
                "night_invite",
                f"{user.username} invited you to {night.name}",
                payload={"night_id": str(night.id), "host": user.username},
                push_title="Watch night",
            )

    await db.flush()
    result = await _serialize(db, night, user)
    await db.commit()
    return result


@router.post(
    "/nights/{night_id}/reply", response_model=NightOut, dependencies=[Depends(csrf_protect)]
)
async def reply_to_invite(
    night_id: str,
    coming: bool,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NightOut:
    night = await _load(db, night_id, user)
    member = (
        await db.execute(
            select(NightMember).where(
                NightMember.night_id == night.id, NightMember.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="you were not invited to this one")
    member.status = "accepted" if coming else "declined"
    member.responded_at = datetime.now(UTC)

    host = (await db.execute(select(User).where(User.id == night.host_id))).scalar_one_or_none()
    if host is not None and host.id != user.id:
        word = "is coming to" if coming else "cannot make"
        await notifications.notify(
            db,
            host,
            "night_invite",
            f"{user.username} {word} {night.name}",
            payload={"night_id": str(night.id)},
            push_title="Watch night",
        )
    await db.flush()
    result = await _serialize(db, night, user)
    await db.commit()
    return result


async def _participant(db: AsyncSession, night: WatchNight, user: User) -> None:
    """Only people who said yes can shape the night."""
    member = (
        await db.execute(
            select(NightMember).where(
                NightMember.night_id == night.id, NightMember.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if member is None or member.status != "accepted":
        raise HTTPException(status_code=403, detail="accept the invitation first")


class PickBody(BaseModel):
    type: str
    tmdb_id: int


@router.post(
    "/nights/{night_id}/queue", response_model=NightOut, dependencies=[Depends(csrf_protect)]
)
async def add_to_queue(
    night_id: str,
    body: PickBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NightOut:
    from app.catalog import ingest

    night = await _load(db, night_id, user)
    await _participant(db, night, user)
    if night.status != "planning":
        raise HTTPException(status_code=409, detail="this night is already settled")
    if body.type not in ("movie", "tv"):
        raise HTTPException(status_code=422, detail="type must be movie or tv")

    count = len(
        (await db.execute(select(NightPick).where(NightPick.night_id == night.id))).scalars().all()
    )
    if count >= MAX_QUEUE:
        raise HTTPException(status_code=409, detail="the queue is full")

    title = await ingest.ensure_title(db, body.type, body.tmdb_id)
    already = (
        await db.execute(
            select(NightPick).where(NightPick.night_id == night.id, NightPick.title_id == title.id)
        )
    ).scalar_one_or_none()
    if already is None:
        # Suggesting something is also a vote for it.
        db.add(
            NightPick(
                night_id=night.id,
                title_id=title.id,
                suggested_by=user.id,
                voter_ids=[str(user.id)],
            )
        )
        await db.flush()
    result = await _serialize(db, night, user)
    await db.commit()
    return result


@router.post(
    "/nights/{night_id}/vote", response_model=NightOut, dependencies=[Depends(csrf_protect)]
)
async def vote_for_pick(
    night_id: str,
    body: PickBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NightOut:
    night = await _load(db, night_id, user)
    await _participant(db, night, user)
    title = (
        await db.execute(
            select(Title).where(Title.type == body.type, Title.tmdb_id == body.tmdb_id)
        )
    ).scalar_one_or_none()
    pick = None
    if title is not None:
        pick = (
            await db.execute(
                select(NightPick).where(
                    NightPick.night_id == night.id, NightPick.title_id == title.id
                )
            )
        ).scalar_one_or_none()
    if pick is None:
        raise HTTPException(status_code=404, detail="that is not in the queue")
    voters = list(pick.voter_ids or [])
    me = str(user.id)
    # Pressing it again takes the vote back, so it is a toggle and not a
    # decision you can only make once.
    pick.voter_ids = [v for v in voters if v != me] if me in voters else voters + [me]
    await db.flush()
    result = await _serialize(db, night, user)
    await db.commit()
    return result


@router.delete(
    "/nights/{night_id}/queue", response_model=NightOut, dependencies=[Depends(csrf_protect)]
)
async def remove_from_queue(
    night_id: str,
    type: str,
    tmdb_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NightOut:
    night = await _load(db, night_id, user)
    await _participant(db, night, user)
    title = (
        await db.execute(select(Title).where(Title.type == type, Title.tmdb_id == tmdb_id))
    ).scalar_one_or_none()
    if title is not None:
        pick = (
            await db.execute(
                select(NightPick).where(
                    NightPick.night_id == night.id, NightPick.title_id == title.id
                )
            )
        ).scalar_one_or_none()
        # Only the person who suggested it, or the host, can take it out.
        if pick is not None and (pick.suggested_by == user.id or night.host_id == user.id):
            await db.delete(pick)
            await db.flush()
    result = await _serialize(db, night, user)
    await db.commit()
    return result


class WatchedBody(BaseModel):
    type: str
    tmdb_id: int


@router.post(
    "/nights/{night_id}/watched", response_model=NightOut, dependencies=[Depends(csrf_protect)]
)
async def mark_watched(
    night_id: str,
    body: WatchedBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NightOut:
    """The host says what was watched. It goes into every participant's
    history there and then, so nobody logs it twice."""
    from app.catalog import ingest

    night = await _load(db, night_id, user)
    if night.host_id != user.id:
        raise HTTPException(status_code=403, detail="only the host can settle the night")
    if body.type not in ("movie", "tv"):
        raise HTTPException(status_code=422, detail="type must be movie or tv")

    title = await ingest.ensure_title(db, body.type, body.tmdb_id)
    now = datetime.now(UTC)
    night.watched_title_id = title.id
    night.watched_at = now
    night.status = "watched"

    coming = (
        (
            await db.execute(
                select(NightMember).where(
                    NightMember.night_id == night.id, NightMember.status == "accepted"
                )
            )
        )
        .scalars()
        .all()
    )
    for member in coming:
        existing = (
            await db.execute(
                select(WatchEvent).where(
                    WatchEvent.user_id == member.user_id,
                    WatchEvent.title_id == title.id,
                    WatchEvent.watched_at >= now - timedelta(hours=12),
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                WatchEvent(
                    user_id=member.user_id,
                    title_id=title.id,
                    watched_at=now,
                    source="watch_night",
                )
            )
    await db.flush()
    result = await _serialize(db, night, user)
    await db.commit()
    return result


class VerdictBody(BaseModel):
    rating_10: int | None = Field(default=None, ge=1, le=10)
    loved: bool = False
    note: str | None = Field(default=None, max_length=1000)


@router.post(
    "/nights/{night_id}/verdict", response_model=NightOut, dependencies=[Depends(csrf_protect)]
)
async def give_verdict(
    night_id: str,
    body: VerdictBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NightOut:
    """What you thought, once you have had time to think it.

    This is not a separate opinion filed away somewhere: it updates your own
    watch event, so the recommendation engine learns from it exactly as it
    would from any other rating."""
    from app.ai import taste as taste_module

    night = await _load(db, night_id, user)
    if night.status != "watched" or night.watched_title_id is None:
        raise HTTPException(status_code=409, detail="nothing has been watched yet")
    await _participant(db, night, user)

    verdict = (
        await db.execute(
            select(NightVerdict).where(
                NightVerdict.night_id == night.id, NightVerdict.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if verdict is None:
        verdict = NightVerdict(night_id=night.id, user_id=user.id)
        db.add(verdict)
    verdict.rating_10 = body.rating_10
    verdict.loved = body.loved
    verdict.note = body.note

    event = (
        (
            await db.execute(
                select(WatchEvent)
                .where(
                    WatchEvent.user_id == user.id,
                    WatchEvent.title_id == night.watched_title_id,
                )
                .order_by(WatchEvent.watched_at.desc())
            )
        )
        .scalars()
        .first()
    )
    if event is not None:
        event.rating_10 = body.rating_10
        event.loved = body.loved
    # A new rating changes what this person should be shown next.
    await taste_module.invalidate_taste(db, user)

    await db.flush()
    result = await _serialize(db, night, user)
    await db.commit()
    return result


async def ask_for_verdicts(db: AsyncSession) -> dict[str, int]:
    """Worker job: ask everyone what they thought, once the wait is over.

    Runs on a schedule rather than on a timer per night, so a restart never
    loses a pending question."""
    counters = {"nights": 0, "asked": 0}
    nights = (
        (
            await db.execute(
                select(WatchNight).where(
                    WatchNight.status == "watched",
                    WatchNight.surveyed_at.is_(None),
                    WatchNight.watched_title_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for night in nights:
        if not _survey_due(night):
            continue
        counters["nights"] += 1
        title = (
            await db.execute(select(Title).where(Title.id == night.watched_title_id))
        ).scalar_one_or_none()
        members = (
            (
                await db.execute(
                    select(NightMember).where(
                        NightMember.night_id == night.id, NightMember.status == "accepted"
                    )
                )
            )
            .scalars()
            .all()
        )
        answered = {
            v.user_id
            for v in (
                await db.execute(select(NightVerdict).where(NightVerdict.night_id == night.id))
            )
            .scalars()
            .all()
        }
        for member in members:
            if member.user_id in answered:
                continue
            person = (
                await db.execute(select(User).where(User.id == member.user_id))
            ).scalar_one_or_none()
            if person is None:
                continue
            name = title.name if title else "what you watched"
            made = await notifications.notify(
                db,
                person,
                "night_survey",
                f"What did you think of {name}?",
                title=title,
                payload={"night_id": str(night.id)},
                push_title=night.name,
            )
            counters["asked"] += 1 if made else 0
        night.surveyed_at = datetime.now(UTC)
        await db.commit()
    return counters


class SuggestBody(BaseModel):
    # How much each person's taste counts, by username. Anyone missing
    # weighs 1. The range is deliberately narrow: past about 3 the blend is
    # just one person's taste wearing everyone else's name.
    weights: dict[str, float] = Field(default_factory=dict)
    # Titles already shown, so "more like these" does not repeat itself.
    seen: list[int] = Field(default_factory=list)


class Suggestion(BaseModel):
    tmdb_id: int
    type: str
    name: str
    poster_path: str | None
    year: int | None
    tmdb_rating: float | None
    # Whose taste this pick is closest to, so a group can see why it is here.
    closest_to: str | None = None
    in_queue: bool = False


class SuggestionsOut(BaseModel):
    results: list[Suggestion]
    # Everyone taken into account, and anyone who had to be left out.
    considered: list[str]
    without_taste: list[str]


@router.post(
    "/nights/{night_id}/suggestions",
    response_model=SuggestionsOut,
    dependencies=[Depends(csrf_protect)],
)
async def suggest_for_night(
    night_id: str,
    body: SuggestBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SuggestionsOut:
    """What everyone in the room would sit through.

    The blend is a weighted average of each person's taste vector, then the
    normal diversified ranking over it. Everything anyone present has
    already seen is excluded, because the one thing a group pick must not be
    is a rewatch for somebody."""
    import numpy as np

    from app.ai import client as ai_client
    from app.ai import taste as taste_module

    night = await _load(db, night_id, user)
    await _participant(db, night, user)

    coming = (
        (
            await db.execute(
                select(NightMember).where(
                    NightMember.night_id == night.id, NightMember.status == "accepted"
                )
            )
        )
        .scalars()
        .all()
    )
    people = (
        (await db.execute(select(User).where(User.id.in_([m.user_id for m in coming]))))
        .scalars()
        .all()
    )

    tastes: list[np.ndarray] = []
    weights: list[float] = []
    owners: list[str] = []
    without: list[str] = []
    exclude: set[uuid.UUID] = set()
    languages: list[str] = []

    try:
        for person in people:
            # Everyone present is excluded from the results whether or not
            # they have a taste vector yet.
            exclude |= await taste_module.watched_title_ids(db, person)
            languages.extend((person.prefs or {}).get("languages", []))
            vector = await taste_module.get_taste(db, person)
            if vector is None:
                without.append(person.username)
                continue
            tastes.append(vector)
            # Clamped: a slider is a nudge, not a veto.
            weights.append(max(0.1, min(3.0, body.weights.get(person.username, 1.0))))
            owners.append(person.username)

        if not tastes:
            return SuggestionsOut(
                results=[], considered=[], without_taste=[p.username for p in people]
            )

        blended = taste_module.blend_tastes(tastes, weights)
        ranked = await taste_module.diversified_ranking(
            db,
            blended,
            limit=24,
            exclude_title_ids=exclude,
            languages=languages or None,
        )
    except ai_client.AIDisabled as exc:
        raise HTTPException(status_code=503, detail="ai_disabled") from exc
    except ai_client.AIError as exc:
        raise HTTPException(status_code=502, detail="ai_unavailable") from exc

    queued = {
        p.title_id
        for p in (await db.execute(select(NightPick).where(NightPick.night_id == night.id)))
        .scalars()
        .all()
    }
    already = set(body.seen)

    out = []
    for title, _ in ranked:
        if not title.poster_path or title.tmdb_id in already:
            continue
        out.append(
            Suggestion(
                tmdb_id=title.tmdb_id,
                type=title.type,
                name=title.name,
                poster_path=title.poster_path,
                year=title.year,
                tmdb_rating=title.tmdb_rating,
                closest_to=await _closest_owner(db, title, tastes, owners),
                in_queue=title.id in queued,
            )
        )
        if len(out) >= 12:
            break

    await db.commit()
    return SuggestionsOut(results=out, considered=owners, without_taste=without)


async def _closest_owner(
    db: AsyncSession, title: Title, tastes: list, owners: list[str]
) -> str | None:
    """Whose taste this pick sits nearest to.

    Only worth saying when more than one person is in the blend, and only
    when one of them is clearly nearer than the rest: a label that is right
    by a rounding error tells the room nothing."""
    if len(owners) < 2:
        return None
    import numpy as np

    from app.ai import client as ai_client
    from app.models import TitleEmbedding

    settings = await ai_client.get_ai_settings(db)
    row = (
        await db.execute(
            select(TitleEmbedding).where(
                TitleEmbedding.title_id == title.id,
                TitleEmbedding.model == settings.embed_model,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    vector = np.array(row.embedding)
    scores = [float(np.dot(taste, vector)) for taste in tastes]
    best = max(range(len(scores)), key=lambda i: scores[i])
    ordered = sorted(scores, reverse=True)
    if len(ordered) > 1 and ordered[0] - ordered[1] < 0.02:
        return None
    return owners[best]
