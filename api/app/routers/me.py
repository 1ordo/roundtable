from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_session, get_current_user
from app.auth.sessions import csrf_token_for
from app.countries import for_user as all_countries
from app.db import get_db
from app.models import Session, User

router = APIRouter(prefix="/api")


class MeUser(BaseModel):
    id: str
    username: str
    email: str | None
    role: str
    avatar_path: str | None
    country_code: str | None
    services: list
    prefs: dict
    visibility: str = "friends"
    handle: str | None = None
    display_name: str | None = None
    # Every country this person follows, the main one first.
    countries: list[str] = []


class MeResponse(BaseModel):
    user: MeUser
    csrf: str
    needs_onboarding: bool


@router.get("/me", response_model=MeResponse)
async def me(session: Session = Depends(get_current_session)) -> MeResponse:
    user = session.user
    prefs = user.prefs or {}
    return MeResponse(
        user=MeUser(
            id=str(user.id),
            username=user.username,
            email=user.email,
            role=user.role,
            avatar_path=user.avatar_path,
            country_code=user.country_code,
            services=user.services or [],
            prefs=prefs,
            visibility=user.visibility,
            handle=user.handle,
            display_name=user.display_name,
            countries=all_countries(user),
        ),
        csrf=csrf_token_for(session.token_hash),
        needs_onboarding=user.country_code is None and not prefs.get("languages"),
    )


class SeedPoster(BaseModel):
    tmdb_id: int
    type: str
    name: str
    poster_path: str | None


class SeedOut(BaseModel):
    posters: list[SeedPoster]


@router.get("/onboarding/popular", response_model=SeedOut)
async def onboarding_seed(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> SeedOut:
    """Well known titles to pick from on the way in.

    Spread across genres rather than straight down the popularity list, so
    the choices actually distinguish one person from another. Twelve of the
    same superhero films would tell the algorithm nothing."""
    from app.models import Title

    rows = (
        (
            await db.execute(
                select(Title)
                .where(Title.poster_path.is_not(None), Title.tmdb_votes > 800)
                .order_by(Title.popularity.desc().nulls_last())
                .limit(400)
            )
        )
        .scalars()
        .all()
    )

    # Round robin by leading genre: take the most popular of each in turn,
    # then the next, so the grid is varied from the first screen.
    by_genre: dict[int, list[Title]] = {}
    for title in rows:
        genres = title.genres or []
        key = int(genres[0].get("id", 0)) if genres else 0
        by_genre.setdefault(key, []).append(title)

    spread: list[Title] = []
    depth = 0
    while len(spread) < 48 and depth < 20:
        added = False
        for bucket in by_genre.values():
            if depth < len(bucket):
                spread.append(bucket[depth])
                added = True
            if len(spread) >= 48:
                break
        if not added:
            break
        depth += 1

    return SeedOut(
        posters=[
            SeedPoster(tmdb_id=t.tmdb_id, type=t.type, name=t.name, poster_path=t.poster_path)
            for t in spread
        ]
    )
