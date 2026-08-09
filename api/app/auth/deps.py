import hmac

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.sessions import SESSION_COOKIE, csrf_token_for, get_session_by_token
from app.db import get_db
from app.models import Session, User

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _has_bearer(request: Request) -> bool:
    return request.headers.get("authorization", "").lower().startswith("bearer wdk_")


async def get_current_session(request: Request, db: AsyncSession = Depends(get_db)) -> Session:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="not authenticated")
    session = await get_session_by_token(db, token)
    if session is None:
        raise HTTPException(status_code=401, detail="session expired")
    return session


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """Browser session or personal API token; the token path enforces the
    global and per-user gates, scopes, and rate limit."""
    if _has_bearer(request):
        from app.auth.tokens import resolve_bearer_user

        resolved = await resolve_bearer_user(request, db)
        if resolved is not None:
            await db.commit()
            return resolved[0]
    session = await get_current_session(request, db)
    if not session.user.is_active:
        raise HTTPException(status_code=401, detail="account disabled")
    return session.user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="admin only")
    return user


async def csrf_protect(request: Request, db: AsyncSession = Depends(get_db)) -> None:
    """Double-submit CSRF for cookie sessions. Bearer-token requests carry no
    ambient credentials, so CSRF does not apply to them.

    The bearer exemption only holds when the token actually authenticates:
    otherwise a forged cross-site request could add a bogus Authorization
    header, skip the CSRF check, and still ride the session cookie."""
    if request.method not in UNSAFE_METHODS:
        return
    if _has_bearer(request):
        from app.auth.tokens import resolve_bearer_user

        if await resolve_bearer_user(request, db) is not None:
            return
        raise HTTPException(status_code=401, detail="invalid or revoked token")
    session = await get_current_session(request, db)
    header = request.headers.get("x-csrf-token", "")
    expected = csrf_token_for(session.token_hash)
    if not hmac.compare_digest(header, expected):
        raise HTTPException(status_code=403, detail="csrf token missing or invalid")
