"""Bearer-token authentication for the personal API and the MCP server.

Gated twice: the api_tokens feature flag (admin, global) and the per-user
api_enabled switch. Scopes: read (GET only) or write."""

import hashlib
import logging
import secrets
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import audit
from app.config import get_settings
from app.db import get_db
from app.models import ApiToken, FeatureFlag, User

logger = logging.getLogger("watchpile.tokens")

TOKEN_PREFIX = "wdk_"
RATE_LIMIT_PER_MINUTE = 120


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


async def api_tokens_enabled(db: AsyncSession) -> bool:
    flag = (
        await db.execute(select(FeatureFlag).where(FeatureFlag.key == "api_tokens"))
    ).scalar_one_or_none()
    return bool(flag and flag.enabled)


async def _rate_limit_ok(token_hash: str) -> bool:
    """Fixed-window per-token limiter in Redis. Fails open: a broken Redis
    must not take the API down."""
    try:
        from redis.asyncio import Redis

        redis = Redis.from_url(get_settings().redis_url)
        try:
            key = f"rl:{token_hash}:{datetime.now(UTC).strftime('%Y%m%d%H%M')}"
            count = await redis.incr(key)
            await redis.expire(key, 90)
            return count <= RATE_LIMIT_PER_MINUTE
        finally:
            await redis.aclose()
    except Exception:
        logger.warning("rate limiter unavailable, failing open")
        return True


async def resolve_bearer_user(
    request: Request, db: AsyncSession, enforce_method_scope: bool = True
) -> tuple[User, ApiToken] | None:
    """Resolve a personal API token to its owner.

    enforce_method_scope reads a read-only token's permission off the HTTP
    method, which is right for the REST API and wrong for anything that
    tunnels reads through POST. MCP is JSON-RPC over POST, so every call
    including watch_history looked like a write and a read-only token could
    not use a single tool. Callers that pass False must check the scope
    themselves, per operation.
    """
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    raw = header[7:].strip()
    if not raw.startswith(TOKEN_PREFIX):
        return None
    token = (
        await db.execute(select(ApiToken).where(ApiToken.token_hash == hash_token(raw)))
    ).scalar_one_or_none()
    if token is None or token.revoked_at is not None:
        raise HTTPException(status_code=401, detail="invalid or revoked token")
    if not await api_tokens_enabled(db):
        raise HTTPException(status_code=403, detail="personal API access is turned off")
    user = (await db.execute(select(User).where(User.id == token.user_id))).scalar_one_or_none()
    if user is None or not user.is_active or not user.api_enabled:
        raise HTTPException(status_code=403, detail="API access is not enabled for this account")
    if enforce_method_scope and request.method != "GET" and "write" not in (token.scopes or []):
        raise HTTPException(status_code=403, detail="this token is read-only")
    if not await _rate_limit_ok(token.token_hash):
        raise HTTPException(status_code=429, detail="rate limit exceeded")

    now = datetime.now(UTC)
    previous = token.last_used_at
    if previous is not None and previous.tzinfo is None:
        previous = previous.replace(tzinfo=UTC)
    # One audit row per token per day keeps the log useful, not noisy.
    if previous is None or previous.date() != now.date():
        await audit(
            db,
            "token.use",
            actor=user,
            request=request,
            object_type="api_token",
            object_id=str(token.id),
        )
    token.last_used_at = now
    await db.flush()
    return user, token


async def get_user_from_session_or_token(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    """Session cookie first, then bearer token. Used by API-facing routes."""
    from app.auth.deps import get_current_session

    resolved = await resolve_bearer_user(request, db)
    if resolved is not None:
        await db.commit()
        return resolved[0]
    session = await get_current_session(request, db)
    if not session.user.is_active:
        raise HTTPException(status_code=401, detail="account disabled")
    return session.user
