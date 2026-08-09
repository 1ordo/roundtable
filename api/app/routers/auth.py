import secrets

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import audit
from app.auth import dev, oidc, passwords
from app.auth.deps import csrf_protect, get_current_session
from app.auth.preauth import PREAUTH_COOKIE, dump_preauth, load_preauth
from app.auth.service import LoginNotAllowed, upsert_user_from_claims
from app.auth.sessions import SESSION_COOKIE, create_session, revoke_session
from app.config import get_settings
from app.db import get_db
from app.models import Session

router = APIRouter()


def _safe_next(next_url: str | None) -> str:
    """Only same-origin relative paths, so the login flow cannot be used as an
    open redirect."""
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return "/app"


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else None


@router.get("/auth/login")
async def login(
    request: Request,
    next: str | None = None,
    as_user: str | None = Query(default=None, alias="as"),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    settings = get_settings()

    if settings.dev_login_enabled:
        # Local development: no identity server, sign straight in. Add
        # ?as=Nadia to switch person and test the shared and group features.
        user = await dev.dev_login_user(db, as_user)
        _, token = await create_session(
            db, user, _client_ip(request), request.headers.get("user-agent")
        )
        await audit(db, "auth.login", actor=user, request=request, detail={"dev": True})
        await db.commit()
        response = RedirectResponse(_safe_next(next), status_code=302)
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=settings.session_ttl_days * 86400,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            path="/",
        )
        return response

    auth_settings = await passwords.get_auth_settings(db)
    if not auth_settings.oidc_enabled:
        await db.commit()
        return RedirectResponse("/login?error=oidc_disabled", status_code=302)
    if not settings.oidc_client_id:
        await db.commit()
        return RedirectResponse("/login?error=oidc_not_configured", status_code=302)
    await db.commit()

    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    verifier, challenge = oidc.make_pkce_pair()
    url = await oidc.provider.authorize_url(state, nonce, challenge)
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(
        PREAUTH_COOKIE,
        dump_preauth(
            {"state": state, "nonce": nonce, "verifier": verifier, "next": _safe_next(next)}
        ),
        max_age=settings.preauth_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/auth",
    )
    return response


@router.get("/auth/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    settings = get_settings()
    if error or not code or not state:
        return RedirectResponse(f"/login?error={error or 'missing_code'}", status_code=302)

    preauth = load_preauth(request.cookies.get(PREAUTH_COOKIE, ""))
    if preauth is None or not secrets.compare_digest(preauth.get("state", ""), state):
        return RedirectResponse("/login?error=state_mismatch", status_code=302)

    try:
        tokens = await oidc.provider.exchange_code(code, preauth["verifier"])
        claims = await oidc.provider.verify_id_token(tokens["id_token"], preauth["nonce"])
    except oidc.OIDCError:
        await audit(db, "auth.failed", request=request, detail={"reason": "oidc_error"})
        await db.commit()
        return RedirectResponse("/login?error=oidc_failed", status_code=302)

    auth_settings = await passwords.get_auth_settings(db)
    if not auth_settings.oidc_enabled:
        await db.commit()
        return RedirectResponse("/login?error=oidc_disabled", status_code=302)

    try:
        user = await upsert_user_from_claims(db, claims)
    except LoginNotAllowed as exc:
        await audit(
            db,
            "auth.denied",
            request=request,
            detail={"reason": exc.reason, "sub": claims.get("sub")},
        )
        await db.commit()
        return RedirectResponse("/login?error=denied", status_code=302)

    _, token = await create_session(
        db, user, _client_ip(request), request.headers.get("user-agent")
    )
    await audit(db, "auth.login", actor=user, request=request)
    await db.commit()

    response = RedirectResponse(_safe_next(preauth.get("next")), status_code=302)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.delete_cookie(PREAUTH_COOKIE, path="/auth")
    return response


@router.post("/api/auth/logout", dependencies=[Depends(csrf_protect)])
async def logout(
    request: Request,
    session: Session = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await revoke_session(db, session)
    await audit(db, "auth.logout", actor=session.user, request=request)
    await db.commit()
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
