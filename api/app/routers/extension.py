"""What the browser extension reports.

The extension sees a title and a playback position on a streaming site. It
does not know what that title is in the catalog, and it should not: matching
is the server's job, where the catalog and the search already live.

Two rules shape this:

  a view is not a watch    reaching a page means interest. Reaching the end
                           means you watched it. Those are recorded
                           differently, and the threshold is deliberate
                           rather than "the tab was open".
  never log the same       a series episode and a film both report the same
  sitting twice            title repeatedly as playback advances. A watch is
                           recorded once per title per day.
"""

import re
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import get_user_from_session_or_token
from app.db import get_db
from app.models import Interaction, Title, User, WatchEvent

router = APIRouter(prefix="/api/extension")

# How far through counts as watched. Credits run long, and nobody watches
# the last eight percent of anything.
WATCHED_AT = 0.88
# A second report of the same title inside this window is the same sitting.
SAME_SITTING = timedelta(hours=6)

# The services themselves, so a part of a split title that is only the
# service name can be dropped outright. Picking the longest remaining part
# is not enough on its own: "Shogun | Disney+" would choose Disney+.
SERVICES = {
    "netflix",
    "prime video",
    "amazon prime video",
    "disney",
    "disneyplus",
    "shahid",
    "mbc shahid",
    "osn",
    "max",
    "hbo max",
    "apple tv",
    "hulu",
    "crunchyroll",
    "watch",
}


def _is_service(part: str) -> bool:
    """Both sides normalised the same way, or "Disney+" fails to match
    "disney+" once the plus has been stripped from only one of them."""
    return part.lower().strip().strip("+").strip() in SERVICES


# Words that appear in a scraped title but never in a catalog one. The box
# set phrasing is here because a store front sells "The Complete First
# Season" while a catalog just calls it by name.
NOISE = re.compile(
    r"\b(watch|stream|online|full episode|episode \d+|season \d+|s\d+e\d+|hd|4k|dub|subbed)\b",
    re.IGNORECASE,
)
BOX_SET = re.compile(
    r"[:\-–]?\s*\bthe complete\b.*$|[:\-–]\s*\b(first|second|third|fourth|fifth|sixth|"
    r"seventh|eighth|ninth|tenth|final)\s+season\b.*$",
    re.IGNORECASE,
)


class Activity(BaseModel):
    # What the page thinks it is showing.
    title: str = Field(min_length=1, max_length=300)
    # Which service, for the record and for the availability hint.
    site: str = Field(min_length=1, max_length=40)
    year: int | None = Field(default=None, ge=1870, le=2200)
    season: int | None = Field(default=None, ge=0, le=100)
    episode: int | None = Field(default=None, ge=0, le=2000)
    # 0 to 1. Absent means the page was open but nothing was playing.
    progress: float | None = Field(default=None, ge=0, le=1)
    kind: str | None = Field(default=None, pattern="^(movie|tv)$")


class ActivityResult(BaseModel):
    # What the server decided, so the popup can show it and a wrong match is
    # visible rather than silent.
    matched: bool
    name: str | None = None
    tmdb_id: int | None = None
    type: str | None = None
    poster_path: str | None = None
    # viewed | watched | saved | removed | ignored | unmatched
    action: str


def clean_title(raw: str) -> str:
    """Strip what players add and catalogs do not have.

    Deliberately conservative: it removes decoration, never words that might
    be part of a real name."""
    text = raw.strip()
    # "Prime Video: Foo", "Foo | MBC Shahid", "Watch Foo | Netflix"
    for separator in ("|", "•", "–", " - "):
        if separator not in text:
            continue
        parts = [p.strip() for p in text.split(separator) if p.strip()]
        # Drop the parts that are only a service name, then take the longest
        # of what is left. Length alone would pick "Disney+" over "Shogun".
        kept = [p for p in parts if not _is_service(p)]
        if kept:
            text = max(kept, key=len)
        elif parts:
            text = parts[0]
    text = re.sub(r"^(prime video|netflix|watch|shahid|osn\+?)\s*[:\-]\s*", "", text, flags=re.I)
    text = BOX_SET.sub("", text)
    text = NOISE.sub(" ", text)
    # A slug from a URL: hyphens are word breaks.
    if "-" in text and " " not in text:
        text = text.replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip(" -:|")
    return text


def _normalise(name: str) -> str:
    """For comparing two titles that mean the same thing.

    Ampersands, punctuation and articles differ between a store front and a
    catalog for the same film, and none of those differences are meaningful."""
    text = name.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


async def _match(db: AsyncSession, name: str, year: int | None, kind: str | None) -> Title | None:
    """Find the catalog row this is most likely to be.

    Local first, because the extension fires constantly and every miss that
    reaches TMDB costs a request.

    How close the name is has to outrank how popular the title is. Ranking
    by popularity made "Legally Blonde 2: Red, White And Blonde" match
    "Legally Blonde", because the first film is better known and neither was
    an exact string match."""
    from difflib import SequenceMatcher

    from app.catalog import local

    wanted = _normalise(name)

    # The search is a LIKE on the whole string, so one character of
    # difference finds nothing: "Legally Blonde 2: Red, White And Blonde"
    # never retrieves "...Red, White & Blonde". Widening to the first few
    # words gets the right row in front of the scorer, which then picks
    # between them properly.
    candidates = await local.search(db, name, limit=25)
    words = name.split()
    if len(words) > 2:
        for take in (3, 2):
            if len(candidates) >= 3:
                break
            candidates += await local.search(db, " ".join(words[:take]), limit=25)
    # Same row can arrive from more than one search.
    candidates = list({c.id: c for c in candidates}.values())
    if not candidates:
        return None

    lowered = name.lower()

    def score(title: Title) -> tuple[float, int, float]:
        similarity = SequenceMatcher(None, wanted, _normalise(title.name)).ratio()
        if _normalise(title.name) == wanted:
            similarity = 1.0
        right_year = 1 if year and title.year == year else 0
        right_kind = 0 if kind and title.type != kind else 1
        # Similarity dominates; year and kind break ties between near equals.
        return (round(similarity, 3), right_year + right_kind, title.popularity or 0)

    best = max(candidates, key=score)
    # A name that is not close to anything is better left unmatched than
    # attached to whatever happened to score highest.
    if SequenceMatcher(None, wanted, _normalise(best.name)).ratio() < 0.6:
        return None
    # A partial match on a short query is usually wrong: "The Order" should
    # not match "The Order of Things" when nothing else agrees.
    if best.name.lower() != lowered and len(name) < 8:
        return None
    if kind and best.type != kind and best.name.lower() != lowered:
        return None
    return best


@router.get("/hello")
async def hello(
    user: User = Depends(get_user_from_session_or_token),
) -> dict:
    """Confirms a token, and says which services this person subscribes to.

    The extension covers every service the app knows, but only reports from
    the ones ticked in Settings. Logging a Netflix film for someone who does
    not have Netflix is either a shared machine or a mistake, and neither is
    something to record silently."""
    from app.catalog.services import SERVICES

    subscribed = set(user.services or [])
    return {
        "ok": True,
        "username": user.display_name or user.handle or user.username,
        "handle": user.handle,
        # Empty means they have not picked any, in which case the extension
        # reports from everything rather than nothing.
        "providers": sorted(subscribed),
        "known": [{"id": s["id"], "name": s["name"]} for s in SERVICES],
    }


@router.post("/activity", response_model=ActivityResult)
async def activity(
    body: Activity,
    request: Request,
    user: User = Depends(get_user_from_session_or_token),
    db: AsyncSession = Depends(get_db),
) -> ActivityResult:
    """One report from a streaming page."""
    name = clean_title(body.title)
    if len(name) < 2:
        return ActivityResult(matched=False, action="ignored")

    title = await _match(db, name, body.year, body.kind)
    if title is None:
        # Not in the catalog yet. The crawler will very likely pull it in
        # later, and guessing at a TMDB search on every keystroke of
        # playback is not worth the quota.
        await db.commit()
        return ActivityResult(matched=False, action="unmatched")

    result = ActivityResult(
        matched=True,
        name=title.name,
        tmdb_id=title.tmdb_id,
        type=title.type,
        poster_path=title.poster_path,
        action="viewed",
    )

    # Opening it is a signal on its own, the same as opening it in the app.
    db.add(Interaction(user_id=user.id, title_id=title.id, kind="view"))

    if (body.progress or 0) >= WATCHED_AT:
        from app.ai import taste as taste_module

        episode = None
        if title.type == "tv" and body.season is not None and body.episode is not None:
            from app.catalog import episodes as episodes_service

            episode = await episodes_service.find_episode(db, title, body.season, body.episode)
            if episode is None:
                await episodes_service.sync_series(db, title)
                await db.flush()
                episode = await episodes_service.find_episode(db, title, body.season, body.episode)

        if episode is not None:
            # Deduplicate on the episode, not on a time window. Four episodes
            # in one evening is four watches, and the window would have
            # recorded one of them.
            logged = await episodes_service.mark_watched(db, user, title, episode, source="app")
            result.action = "watched" if logged else "ignored"
            if logged:
                await taste_module.invalidate_taste(db, user)
        else:
            # A film, or a series the page did not number. Fall back to the
            # sitting window, which is the best that can be done without
            # knowing which episode it was.
            recent = (
                await db.execute(
                    select(func.count(WatchEvent.id)).where(
                        WatchEvent.user_id == user.id,
                        WatchEvent.title_id == title.id,
                        WatchEvent.episode_id.is_(None),
                        WatchEvent.watched_at > datetime.now(UTC) - SAME_SITTING,
                    )
                )
            ).scalar_one()
            if recent == 0:
                db.add(WatchEvent(user_id=user.id, title_id=title.id, watched_at=datetime.now(UTC)))
                result.action = "watched"
                await taste_module.invalidate_taste(db, user)
            else:
                result.action = "ignored"

    await db.commit()
    return result


class TitleGuess(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    year: int | None = Field(default=None, ge=1870, le=2200)
    kind: str | None = Field(default=None, pattern="^(movie|tv)$")


class MatchRequest(BaseModel):
    # A whole list scraped off a service in one go.
    titles: list[TitleGuess] = Field(min_length=1, max_length=400)
    site: str = Field(min_length=1, max_length=40)


class MatchedTitle(BaseModel):
    # What was on the page, so an unmatched row can still be shown.
    given: str
    matched: bool
    name: str | None = None
    tmdb_id: int | None = None
    type: str | None = None
    poster_path: str | None = None
    year: int | None = None
    # Already on their watchlist, so the review screen can skip it.
    already: bool = False


class MatchResult(BaseModel):
    results: list[MatchedTitle]
    matched: int
    already: int


@router.post("/match", response_model=MatchResult)
async def match_list(
    body: MatchRequest,
    user: User = Depends(get_user_from_session_or_token),
    db: AsyncSession = Depends(get_db),
) -> MatchResult:
    """Work out what a scraped list actually is, and change nothing.

    Deliberately read only. Importing someone's whole list is not something
    to do because a page was open, so this is the half that shows them what
    would happen and the confirm step is separate."""
    from app.models import List as ListModel
    from app.models import ListItem
    from app.tracking import service as lists_service

    watchlist = await lists_service.ensure_watchlist(db, user)
    on_list = set(
        (await db.execute(select(ListItem.title_id).where(ListItem.list_id == watchlist.id)))
        .scalars()
        .all()
    )

    out: list[MatchedTitle] = []
    # Two rows of the same series arrive as separate cards: "The Mentalist
    # - Season 2" and "The Mentalist: The Complete First Season" both
    # resolve to the same show. Deduplicating on the scraped name keeps
    # both, because the names differ; it has to be done on what they
    # matched to.
    matched_already: set[uuid.UUID] = set()
    for guess in body.titles:
        name = clean_title(guess.title)
        title = await _match(db, name, guess.year, guess.kind) if len(name) >= 2 else None
        if title is None:
            out.append(MatchedTitle(given=guess.title, matched=False))
            continue
        if title.id in matched_already:
            continue
        matched_already.add(title.id)
        out.append(
            MatchedTitle(
                given=guess.title,
                matched=True,
                name=title.name,
                tmdb_id=title.tmdb_id,
                type=title.type,
                poster_path=title.poster_path,
                year=title.year,
                already=title.id in on_list,
            )
        )

    await db.commit()
    _ = ListModel
    return MatchResult(
        results=out,
        matched=sum(1 for r in out if r.matched),
        already=sum(1 for r in out if r.already),
    )


class ImportRequest(BaseModel):
    # Only what the person ticked, by tmdb id, never the raw scrape again.
    titles: list[dict] = Field(min_length=1, max_length=400)


class ImportResult(BaseModel):
    added: int
    already: int
    failed: int


@router.post("/import", response_model=ImportResult, status_code=201)
async def import_list(
    body: ImportRequest,
    request: Request,
    user: User = Depends(get_user_from_session_or_token),
    db: AsyncSession = Depends(get_db),
) -> ImportResult:
    """Add the confirmed titles to the watchlist."""
    from app.audit import audit
    from app.catalog import ingest
    from app.models import ListItem
    from app.tracking import service as lists_service

    watchlist = await lists_service.ensure_watchlist(db, user)
    existing = set(
        (await db.execute(select(ListItem.title_id).where(ListItem.list_id == watchlist.id)))
        .scalars()
        .all()
    )

    added = already = failed = 0
    for entry in body.titles:
        media_type = str(entry.get("type") or "")
        tmdb_id = entry.get("tmdb_id")
        if media_type not in ("movie", "tv") or not isinstance(tmdb_id, int):
            failed += 1
            continue
        try:
            title = await ingest.ensure_title(db, media_type, tmdb_id)
        except Exception:
            failed += 1
            continue
        if title is None:
            failed += 1
            continue
        if title.id in existing:
            already += 1
            continue
        db.add(ListItem(list_id=watchlist.id, title_id=title.id))
        existing.add(title.id)
        added += 1

    await audit(
        db,
        "import.extension",
        actor=user,
        request=request,
        detail={"added": added, "already": already, "failed": failed},
    )
    await db.commit()
    return ImportResult(added=added, already=already, failed=failed)


class RateBody(BaseModel):
    type: str = Field(pattern="^(movie|tv)$")
    tmdb_id: int
    rating_10: int | None = Field(default=None, ge=1, le=10)
    loved: bool = False


@router.post("/rate")
async def rate(
    body: RateBody,
    user: User = Depends(get_user_from_session_or_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Rate the sitting the extension just logged.

    Updates the most recent watch rather than adding another, because the
    extension already recorded that it happened. Rating is the second half
    of the same event, not a new one."""
    from app.ai import taste as taste_module
    from app.catalog import ingest

    title = await ingest.ensure_title(db, body.type, body.tmdb_id)
    if title is None:
        raise HTTPException(status_code=404, detail="title not found")

    event = (
        await db.execute(
            select(WatchEvent)
            .where(WatchEvent.user_id == user.id, WatchEvent.title_id == title.id)
            .order_by(WatchEvent.watched_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if event is None:
        # Rating something the extension never logged still counts, so the
        # rating is not lost to a race.
        event = WatchEvent(user_id=user.id, title_id=title.id, watched_at=datetime.now(UTC))
        db.add(event)

    event.rating_10 = body.rating_10
    event.loved = body.loved
    await taste_module.invalidate_taste(db, user)
    await db.commit()
    return {"ok": True, "name": title.name}


class WatchlistBody(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    site: str = Field(min_length=1, max_length=40)
    year: int | None = Field(default=None, ge=1870, le=2200)
    kind: str | None = Field(default=None, pattern="^(movie|tv)$")
    # False when they took it off the service's list, so the two stay in step.
    add: bool = True


@router.post("/watchlist", response_model=ActivityResult)
async def watchlist(
    body: WatchlistBody,
    user: User = Depends(get_user_from_session_or_token),
    db: AsyncSession = Depends(get_db),
) -> ActivityResult:
    """Mirror a save made on the streaming service itself.

    Pressing Add to Watchlist on Prime and then finding it missing here is
    the kind of gap that makes two lists worse than one, so the click is
    followed rather than waiting for an import."""
    from app.models import ListItem
    from app.tracking import service as lists_service

    name = clean_title(body.title)
    if len(name) < 2:
        return ActivityResult(matched=False, action="ignored")

    title = await _match(db, name, body.year, body.kind)
    if title is None:
        await db.commit()
        return ActivityResult(matched=False, action="unmatched")

    watchlist_row = await lists_service.ensure_watchlist(db, user)
    existing = (
        await db.execute(
            select(ListItem).where(
                ListItem.list_id == watchlist_row.id, ListItem.title_id == title.id
            )
        )
    ).scalar_one_or_none()

    action = "ignored"
    if body.add and existing is None:
        db.add(ListItem(list_id=watchlist_row.id, title_id=title.id))
        action = "saved"
    elif not body.add and existing is not None:
        await db.delete(existing)
        action = "removed"

    await db.commit()
    return ActivityResult(
        matched=True,
        name=title.name,
        tmdb_id=title.tmdb_id,
        type=title.type,
        poster_path=title.poster_path,
        action=action,
    )
