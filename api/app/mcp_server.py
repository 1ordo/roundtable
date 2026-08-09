"""MCP server mounted at /api/mcp. Claude sessions connect with a personal
API token in the Authorization header; every tool acts as that user and goes
through the same gates as the REST API."""

from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import ListItem, Title, User

mcp: FastMCP = FastMCP(
    "Watchpile",
    instructions=(
        "Movie and series tracker for the household. Authenticate with a "
        "personal API token (Authorization: Bearer wdk_...). Tools operate "
        "as the token's owner."
    ),
)


async def _authed_user(db: AsyncSession, write: bool = False) -> User:
    """The token's owner, and whether this tool is allowed to change things.

    Scope is checked per tool rather than by HTTP method. Every MCP call is
    a POST, so the method rule would have made a read-only token useless:
    watch_history and list_watchlist were refused along with add_to_list.
    """
    from fastapi import HTTPException

    from app.auth.tokens import resolve_bearer_user

    request = get_http_request()
    try:
        resolved = await resolve_bearer_user(request, db, enforce_method_scope=False)
    except HTTPException as exc:
        raise ToolError(f"authentication failed: {exc.detail}") from exc
    if resolved is None:
        raise ToolError(
            "missing token: send Authorization: Bearer wdk_... "
            "(create one under Settings in Watchpile)"
        )
    user, token = resolved
    if write and "write" not in (token.scopes or []):
        raise ToolError("this token is read-only; it can read your lists but not change them")
    return user


def _card(title: Title) -> dict[str, Any]:
    return {
        "tmdb_id": title.tmdb_id,
        "type": title.type,
        "name": title.name,
        "year": title.year,
    }


@mcp.tool
async def search_titles(query: str) -> list[dict]:
    """Search films and series by name in any language."""
    from app.catalog import tmdb
    from app.db import get_sessionmaker

    async with get_sessionmaker()() as db:
        await _authed_user(db)
        try:
            payload = await tmdb.search_multi(db, query)
        except tmdb.TmdbNotConfigured as exc:
            raise ToolError("the catalog is not configured yet") from exc
        await db.commit()
        return [
            {
                "tmdb_id": item["id"],
                "type": item.get("media_type"),
                "name": item.get("title") or item.get("name"),
                "year": (item.get("release_date") or item.get("first_air_date") or "")[:4],
            }
            for item in payload.get("results", [])
            if item.get("media_type") in ("movie", "tv")
        ][:10]


@mcp.tool
async def list_watchlist() -> list[dict]:
    """The owner's watchlist plus the shared couple list."""
    from app.db import get_sessionmaker
    from app.tracking import service

    async with get_sessionmaker()() as db:
        user = await _authed_user(db)
        out = []
        for lst in await service.visible_lists(db, user):
            items = (
                (
                    await db.execute(
                        select(ListItem)
                        .options(joinedload(ListItem.title))
                        .where(ListItem.list_id == lst.id)
                        .order_by(ListItem.added_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            out.append(
                {
                    "list": lst.name,
                    "kind": lst.kind,
                    "titles": [_card(i.title) for i in items],
                }
            )
        await db.commit()
        return out


@mcp.tool
async def add_to_list(media_type: str, tmdb_id: int, shared: bool = False) -> str:
    """Add a title to the owner's watchlist, or the shared list when
    shared=true. media_type is movie or tv."""
    if media_type not in ("movie", "tv"):
        raise ToolError("media_type must be movie or tv")
    from app.catalog import ingest, tmdb
    from app.db import get_sessionmaker
    from app.tracking import service

    async with get_sessionmaker()() as db:
        user = await _authed_user(db, write=True)
        target = (
            await service.ensure_shared_list(db, user)
            if shared
            else await service.ensure_watchlist(db, user)
        )
        try:
            title = await ingest.ensure_title(db, media_type, tmdb_id)
        except (tmdb.TmdbNotConfigured, tmdb.TmdbError) as exc:
            raise ToolError("could not fetch that title from the catalog") from exc
        await service.add_title_to_list(db, target, title.id, user)
        await db.commit()
        return f"Added {title.name} to {target.name}"


@mcp.tool
async def get_availability(media_type: str, tmdb_id: int) -> dict:
    """Where a title streams, rents, or sells in the household countries."""
    if media_type not in ("movie", "tv"):
        raise ToolError("media_type must be movie or tv")
    from app.catalog import ingest, tmdb
    from app.db import get_sessionmaker
    from app.models import Availability

    async with get_sessionmaker()() as db:
        await _authed_user(db)
        try:
            title = await ingest.ensure_title(db, media_type, tmdb_id)
        except (tmdb.TmdbNotConfigured, tmdb.TmdbError) as exc:
            raise ToolError("could not fetch that title from the catalog") from exc
        countries = {
            u.country_code for u in (await db.execute(select(User))).scalars() if u.country_code
        }
        rows = (
            (await db.execute(select(Availability).where(Availability.title_id == title.id)))
            .scalars()
            .all()
        )
        await db.commit()
        result: dict[str, list[str]] = {}
        for row in rows:
            if countries and row.country not in countries:
                continue
            result.setdefault(row.country, []).append(f"{row.provider_name} ({row.kind})")
        return {"title": title.name, "availability": result or "not on tracked services"}


@mcp.tool
async def mark_watched(
    media_type: str, tmdb_id: int, rating_10: int | None = None, loved: bool = False
) -> str:
    """Log a watch for the token owner, optionally with a 1-10 rating."""
    if media_type not in ("movie", "tv"):
        raise ToolError("media_type must be movie or tv")
    if rating_10 is not None and not 1 <= rating_10 <= 10:
        raise ToolError("rating_10 must be between 1 and 10")
    from app.catalog import ingest, tmdb
    from app.db import get_sessionmaker
    from app.models import WatchEvent

    async with get_sessionmaker()() as db:
        user = await _authed_user(db, write=True)
        try:
            title = await ingest.ensure_title(db, media_type, tmdb_id)
        except (tmdb.TmdbNotConfigured, tmdb.TmdbError) as exc:
            raise ToolError("could not fetch that title from the catalog") from exc
        db.add(
            WatchEvent(
                user_id=user.id,
                title_id=title.id,
                rating_10=rating_10,
                loved=loved,
                source="app",
            )
        )
        await db.commit()
        return f"Logged {title.name} as watched"


mcp_app = mcp.http_app(path="/", stateless_http=True)


@mcp.tool
async def ask_watchpile(question: str) -> dict:
    """Ask the recommendation assistant a question in natural language. It
    reads the owner's lists, history and ratings, and answers only with
    titles that exist in the catalog."""
    from app.ai import chat as chat_module
    from app.ai import client as ai_client
    from app.db import get_sessionmaker

    async with get_sessionmaker()() as db:
        user = await _authed_user(db)
        try:
            result = await chat_module.answer(db, user, question)
        except ai_client.AIDisabled as exc:
            raise ToolError("AI features are turned off for this install") from exc
        except ai_client.AIError as exc:
            raise ToolError("the AI endpoint did not answer") from exc
        await db.commit()
        return {
            "reply": result["reply"],
            "titles": [_card(t) for t in result["titles"]],
        }


@mcp.tool
async def recommendations(limit: int = 10) -> list[dict]:
    """Personal picks for the token owner, ranked by their taste vector with
    the same diversity rules the app uses."""
    from app.ai import client as ai_client
    from app.ai import taste as taste_module
    from app.db import get_sessionmaker

    async with get_sessionmaker()() as db:
        user = await _authed_user(db)
        try:
            vector = await taste_module.get_taste(db, user)
            if vector is None:
                return []
            exclude = await taste_module.watched_title_ids(db, user)
            languages = (user.prefs or {}).get("languages") or None
            ranked = await taste_module.diversified_ranking(
                db, vector, min(limit, 40), exclude, languages=languages
            )
        except ai_client.AIDisabled as exc:
            raise ToolError("AI features are turned off for this install") from exc
        await db.commit()
        return [{**_card(t), "match": round(score * 100)} for t, score in ranked]


@mcp.tool
async def watch_history(limit: int = 25) -> list[dict]:
    """What the owner has watched, most recent first, with their ratings."""
    from app.db import get_sessionmaker
    from app.models import WatchEvent

    async with get_sessionmaker()() as db:
        user = await _authed_user(db)
        events = (
            (
                await db.execute(
                    select(WatchEvent)
                    .options(joinedload(WatchEvent.title))
                    .where(WatchEvent.user_id == user.id)
                    .order_by(WatchEvent.watched_at.desc())
                    .limit(min(limit, 200))
                )
            )
            .scalars()
            .all()
        )
        await db.commit()
        return [
            {
                **_card(event.title),
                "watched_at": event.watched_at.isoformat(),
                "rating_10": event.rating_10,
                "loved": event.loved,
            }
            for event in events
        ]


@mcp.tool
async def rate_title(media_type: str, tmdb_id: int, kind: str) -> str:
    """Teach the algorithm. kind is like or dislike; a dislike also keeps the
    title out of future recommendations."""
    if kind not in ("like", "dislike"):
        raise ToolError("kind must be like or dislike")
    if media_type not in ("movie", "tv"):
        raise ToolError("media_type must be movie or tv")
    from app.db import get_sessionmaker
    from app.models import Interaction, Title

    async with get_sessionmaker()() as db:
        user = await _authed_user(db, write=True)
        title = (
            await db.execute(
                select(Title).where(Title.tmdb_id == tmdb_id, Title.type == media_type)
            )
        ).scalar_one_or_none()
        if title is None:
            raise ToolError("that title is not in the catalog yet; search for it first")
        opposite = "dislike" if kind == "like" else "like"
        from sqlalchemy import delete as sql_delete

        await db.execute(
            sql_delete(Interaction).where(
                Interaction.user_id == user.id,
                Interaction.title_id == title.id,
                Interaction.kind.in_([kind, opposite]),
            )
        )
        db.add(Interaction(user_id=user.id, title_id=title.id, kind=kind))
        await db.commit()
        return f"Recorded: {kind} for {title.name}"


@mcp.tool
async def catalog_stats() -> dict:
    """Size and shape of the catalog, and how much signal the owner has given."""
    from sqlalchemy import func

    from app.db import get_sessionmaker
    from app.models import Interaction, Title, WatchEvent

    async with get_sessionmaker()() as db:
        user = await _authed_user(db)
        titles = (await db.execute(select(func.count(Title.id)))).scalar_one()
        movies = (
            await db.execute(select(func.count(Title.id)).where(Title.type == "movie"))
        ).scalar_one()
        watched = (
            await db.execute(select(func.count(WatchEvent.id)).where(WatchEvent.user_id == user.id))
        ).scalar_one()
        signals = (
            await db.execute(
                select(func.count(Interaction.id)).where(Interaction.user_id == user.id)
            )
        ).scalar_one()
        await db.commit()
        return {
            "titles": titles,
            "films": movies,
            "series": titles - movies,
            "your_watched": watched,
            "your_signals": signals,
        }
