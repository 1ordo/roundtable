import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.config import get_settings
from app.models import Session, User

SESSION_COOKIE = "wd_session"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token_for(token_hash: str) -> str:
    """Deterministic per-session CSRF token: HMAC of the session hash.
    The SPA fetches it from /api/me and sends it back in X-CSRF-Token."""
    key = get_settings().secret_key.encode()
    return hmac.new(key, f"csrf:{token_hash}".encode(), hashlib.sha256).hexdigest()


async def create_session(
    db: AsyncSession, user: User, ip: str | None, user_agent: str | None
) -> tuple[Session, str]:
    token = secrets.token_urlsafe(32)
    session = Session(
        user_id=user.id,
        token_hash=_hash_token(token),
        expires_at=datetime.now(UTC) + timedelta(days=get_settings().session_ttl_days),
        ip=ip,
        user_agent=(user_agent or "")[:400] or None,
    )
    db.add(session)
    await db.flush()
    return session, token


async def get_session_by_token(db: AsyncSession, token: str) -> Session | None:
    result = await db.execute(
        select(Session)
        .options(joinedload(Session.user))
        .where(Session.token_hash == _hash_token(token))
    )
    session = result.scalar_one_or_none()
    if session is None or session.revoked_at is not None:
        return None
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires < datetime.now(UTC):
        return None
    return session


async def revoke_session(db: AsyncSession, session: Session) -> None:
    session.revoked_at = datetime.now(UTC)
    await db.flush()
