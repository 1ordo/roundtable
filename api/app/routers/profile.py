import io
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import audit
from app.auth.deps import csrf_protect, get_current_user
from app.catalog import tmdb
from app.config import get_settings
from app.countries import MAX_COUNTRIES
from app.db import get_db
from app.models import User
from app.routers.catalog import invalidate_home
from app.social import handles

router = APIRouter(prefix="/api")

# The alert kinds a person can switch off, and the only ones the settings
# screen may offer. Every entry must be a kind something actually emits:
# "like" and "shared" used to be listed here and nothing ever sent them,
# while the kinds that were sent were absent, so saving the form muted
# almost everything. Keep this list and app.notifications.service.KINDS in
# step, and keep both in step with the settings UI.
NOTIFY_KINDS = (
    "availability",
    "franchise",
    "episode",
    "cinema",
    "person",
    "social",
    "message",
    "friend_request",
    "night_invite",
    "night_survey",
)

AVATAR_SIZE = 512
MAX_AVATAR_PIXELS = 50_000_000


class UpdateMeBody(BaseModel):
    # The main one: what age ratings and default views follow.
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    # Everywhere else this person cares about. Availability, cinema
    # listings and release alerts cover all of them, because plenty of
    # people split their life across more than one country.
    countries: list[str] | None = None
    services: list[int] | None = None
    # Cultures and languages the person cares about, ISO 639-1 codes.
    languages: list[str] | None = None
    # Favorite genre ids, seed the algorithm before history exists.
    genres: list[int] | None = None
    # Show age ratings and the parents guide throughout the app.
    parents_guide: bool | None = None
    # How far outside the taste cluster suggestions may wander.
    discovery: Literal["comfort", "balanced", "adventurous"] | None = None
    # Keep titles already watched out of the suggestion shelves.
    hide_watched: bool | None = None
    # Suggest only what is on a service this person actually pays for, in a
    # country they set. Off by default, because on a thin catalog it is a
    # sharp restriction; on, it is the difference between a suggestion and a
    # thing you cannot press play on.
    only_my_services: bool | None = None
    # Which media type the browse and home pages open on.
    default_type: Literal["all", "movie", "tv"] | None = None
    # Which alerts to raise; unchecked kinds are never created.
    notify_kinds: list[str] | None = None
    # Honour a manual reduced-motion choice as well as the system one.
    reduce_motion: bool | None = None
    # Email is opted into rather than out of: it is more intrusive than an
    # inbox row.
    email_alerts: bool | None = None
    # A word when a paid service goes a month unused. Opt-in: the app never
    # volunteers opinions about money.
    expense_alerts: bool | None = None
    # Which parts of a profile are shown, one level each. Unset panels fall
    # back to the profile level rather than to a hardcoded default.
    panel_visibility: dict[str, str] | None = None
    # Whether anyone signed in may see this profile, or only friends.
    visibility: Literal["public", "friends", "private"] | None = None
    handle: str | None = Field(default=None, max_length=40)
    display_name: str | None = Field(default=None, max_length=60)


@router.put("/me", dependencies=[Depends(csrf_protect)])
async def update_me(
    body: UpdateMeBody,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    changes: dict = {}
    if body.country_code is not None:
        user.country_code = body.country_code.upper()
        changes["country_code"] = user.country_code
    if body.services is not None:
        user.services = body.services
        changes["services"] = body.services
    if body.visibility is not None:
        user.visibility = body.visibility
        changes["visibility"] = body.visibility
    if body.handle is not None:
        try:
            changes["handle"] = await handles.claim(db, user, body.handle)
        except handles.HandleError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if body.display_name is not None:
        cleaned = body.display_name.strip()
        user.display_name = cleaned or None
        changes["display_name"] = user.display_name
    prefs = dict(user.prefs or {})
    if body.countries is not None:
        codes = []
        for code in body.countries:
            upper = code.strip().upper()[:2]
            if len(upper) == 2 and upper not in codes:
                codes.append(upper)
        prefs["countries"] = codes[:MAX_COUNTRIES]
        changes["countries"] = prefs["countries"]

    if body.languages is not None:
        prefs["languages"] = [code.lower()[:2] for code in body.languages][:10]
        changes["languages"] = prefs["languages"]
    if body.genres is not None:
        prefs["genres"] = body.genres[:15]
        changes["genres"] = prefs["genres"]
    if body.parents_guide is not None:
        prefs["parents_guide"] = body.parents_guide
        changes["parents_guide"] = body.parents_guide
    # The rest are plain flags: one loop rather than a branch each.
    for field in (
        "discovery",
        "hide_watched",
        "only_my_services",
        "default_type",
        "reduce_motion",
        "email_alerts",
        "expense_alerts",
    ):
        flag = getattr(body, field)
        if flag is not None:
            prefs[field] = flag
            changes[field] = flag
    if body.panel_visibility is not None:
        from app.routers.profiles import STAT_PANELS

        panels: dict[str, str] = {
            panel: level
            for panel, level in body.panel_visibility.items()
            if panel in STAT_PANELS and level in ("public", "friends", "private")
        }
        prefs["panel_visibility"] = panels
        changes["panel_visibility"] = panels
    if body.notify_kinds is not None:
        prefs["notify_kinds"] = [k for k in body.notify_kinds if k in NOTIFY_KINDS]
        changes["notify_kinds"] = prefs["notify_kinds"]
    if changes:
        user.prefs = prefs
    if changes:
        await audit(db, "user.update_profile", actor=user, request=request, detail=changes)
    await db.commit()
    # Languages, hide-watched, the dial: all of it shapes home.
    await invalidate_home(str(user.id))
    return {"status": "ok"}


def _avatar_dir() -> Path:
    path = Path(get_settings().data_dir) / "avatars"
    path.mkdir(parents=True, exist_ok=True)
    return path


@router.post("/me/avatar", dependencies=[Depends(csrf_protect)])
async def upload_avatar(
    file: UploadFile,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    raw = await file.read(get_settings().avatar_max_bytes + 1)
    if len(raw) > get_settings().avatar_max_bytes:
        raise HTTPException(status_code=413, detail="image is larger than 5 MB")
    try:
        image = Image.open(io.BytesIO(raw))
        # Format and dimensions are checked before decoding: a few hundred
        # kilobytes of PNG can expand to gigabytes of pixels once loaded.
        if image.format not in ("JPEG", "PNG", "WEBP"):
            raise HTTPException(status_code=400, detail="use a JPEG, PNG, or WebP image")
        if image.size[0] * image.size[1] > MAX_AVATAR_PIXELS:
            raise HTTPException(status_code=413, detail="image dimensions are too large")
        image.draft("RGB", (AVATAR_SIZE, AVATAR_SIZE))
        image.load()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="not a readable image") from exc

    # Re-encoding drops EXIF and any other metadata by construction.
    clean = image.convert("RGB")
    clean.thumbnail((AVATAR_SIZE, AVATAR_SIZE))
    out_path = _avatar_dir() / f"{user.id}.webp"
    clean.save(out_path, "WEBP", quality=88)

    user.avatar_path = f"/api/media/avatars/{user.id}.webp"
    await audit(db, "user.avatar_update", actor=user, request=request)
    await db.commit()
    return {"avatar_path": user.avatar_path}


@router.get("/media/avatars/{filename}")
async def serve_avatar(filename: str, user: User = Depends(get_current_user)) -> FileResponse:
    # Only ever serve the flat avatar directory; no traversal, no other types.
    if "/" in filename or ".." in filename or not filename.endswith(".webp"):
        raise HTTPException(status_code=404, detail="not found")
    path = _avatar_dir() / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(path, media_type="image/webp")


class CountryOption(BaseModel):
    code: str
    name: str


@router.get("/countries", response_model=list[CountryOption])
async def countries(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[CountryOption]:
    """Every country the catalog knows, so the picker is not a short list of
    guesses."""
    try:
        raw = await tmdb.countries(db)
    except (tmdb.TmdbNotConfigured, tmdb.TmdbError):
        # Without the catalog we still offer the ones already in use here.
        raw = []
    await db.commit()
    options = [
        CountryOption(code=c["iso_3166_1"], name=c.get("english_name") or c["iso_3166_1"])
        for c in raw
        if c.get("iso_3166_1")
    ]
    if not options:
        options = [CountryOption(code=code, name=code) for code in ("EG", "MA", "US", "GB", "FR")]
    options.sort(key=lambda c: c.name)
    return options


class ProviderOption(BaseModel):
    provider_id: int
    provider_name: str
    logo_path: str | None


@router.get("/providers", response_model=list[ProviderOption])
async def providers(
    country: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ProviderOption]:
    """Streaming services available in a country, for the profile picker."""
    if len(country) != 2:
        raise HTTPException(status_code=422, detail="country must be a 2-letter code")
    try:
        payload = await tmdb.provider_list(db, country.upper())
    except tmdb.TmdbNotConfigured as exc:
        raise HTTPException(status_code=503, detail="tmdb_not_configured") from exc
    except tmdb.TmdbError as exc:
        raise HTTPException(status_code=502, detail="tmdb_unavailable") from exc
    await db.commit()
    options = [
        ProviderOption(
            provider_id=p["provider_id"],
            provider_name=p.get("provider_name", "Unknown"),
            logo_path=p.get("logo_path"),
        )
        for p in payload.get("results", [])
    ]
    options.sort(key=lambda p: p.provider_name.lower())
    return options


# Poster sizes the proxy will serve. A fixed list, because the path is
# built into a URL on another host and must never be attacker-shaped.
POSTER_SIZES = {"w92", "w185", "w342", "w500", "w780", "w1280", "original"}
POSTER_HOST = "https://image.tmdb.org/t/p"
POSTER_CACHE = 60 * 60 * 24 * 30


@router.get("/media/tmdb/{size}/{filename}")
async def poster_proxy(size: str, filename: str) -> Response:
    """Serve a catalog image from our own origin.

    Two reasons this exists rather than pointing the browser at TMDB:
    the share card draws posters onto a canvas, and a cross-origin image
    with no CORS header taints it so the export silently fails; and it
    keeps the browser from announcing to a third party everything the
    person is looking at."""
    import httpx

    if size not in POSTER_SIZES:
        raise HTTPException(status_code=404, detail="not found")
    # A filename only: no slashes, no traversal, no absolute URL.
    if "/" in filename or ".." in filename or not filename.endswith((".jpg", ".png", ".svg")):
        raise HTTPException(status_code=404, detail="not found")

    try:
        async with httpx.AsyncClient(timeout=15.0) as http:
            upstream = await http.get(f"{POSTER_HOST}/{size}/{filename}")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="image unavailable") from exc
    if upstream.status_code != 200:
        raise HTTPException(status_code=404, detail="not found")

    return Response(
        content=upstream.content,
        media_type=upstream.headers.get("content-type", "image/jpeg"),
        headers={"Cache-Control": f"public, max-age={POSTER_CACHE}, immutable"},
    )
