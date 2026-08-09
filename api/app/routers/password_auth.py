from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import audit
from app.auth import passwords
from app.auth.deps import csrf_protect, get_current_user
from app.auth.sessions import SESSION_COOKIE, create_session
from app.config import get_settings
from app.db import get_db
from app.models import User

router = APIRouter(prefix="/api/auth")

GENERIC_FAILURE = "that username and password do not match"


class AuthMethods(BaseModel):
    oidc: bool
    password: bool
    registration_open: bool
    # No accounts yet, so this is a setup screen rather than a login screen.
    first_run: bool = False


@router.get("/methods", response_model=AuthMethods)
async def methods(db: AsyncSession = Depends(get_db)) -> AuthMethods:
    """Public: the login screen needs this before anyone is signed in."""
    from sqlalchemy import func, select

    from app.models import User

    settings = await passwords.get_auth_settings(db)
    first_run = (await db.execute(select(func.count(User.id)))).scalar_one() == 0
    await db.commit()
    return AuthMethods(
        oidc=settings.oidc_enabled,
        # An empty instance must be able to make its first account even when
        # every switch is off, or a fresh install has no way in.
        password=settings.password_enabled or first_run,
        registration_open=first_run or (settings.password_enabled and settings.registration_open),
        first_run=first_run,
    )


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else None


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=200)


class LoginResult(BaseModel):
    username: str
    role: str


@router.post("/password/login", response_model=LoginResult)
async def password_login(
    body: LoginBody,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> LoginResult:
    settings = await passwords.get_auth_settings(db)
    if not settings.password_enabled:
        raise HTTPException(status_code=403, detail="password sign-in is turned off")

    if await passwords.too_many_attempts(body.username):
        await audit(
            db,
            "auth.failed",
            request=request,
            detail={"reason": "rate_limited", "username": body.username[:120]},
        )
        await db.commit()
        raise HTTPException(
            status_code=429, detail="too many attempts, wait a few minutes and try again"
        )

    user = await passwords.authenticate(db, body.username, body.password)
    if user is None:
        await passwords.record_failure(body.username)
        await audit(
            db,
            "auth.failed",
            request=request,
            detail={"reason": "bad_credentials", "username": body.username[:120]},
        )
        await db.commit()
        raise HTTPException(status_code=401, detail=GENERIC_FAILURE)

    await passwords.clear_failures(body.username)
    _, token = await create_session(
        db, user, _client_ip(request), request.headers.get("user-agent")
    )
    await audit(db, "auth.login", actor=user, request=request, detail={"method": "password"})
    await db.commit()
    _set_session_cookie(response, token)
    return LoginResult(username=user.username, role=user.role)


class RegisterBody(BaseModel):
    username: str = Field(min_length=2, max_length=40)
    password: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=255)


@router.post("/password/register", response_model=LoginResult, status_code=201)
async def password_register(
    body: RegisterBody,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> LoginResult:
    try:
        user = await passwords.register(db, body.username, body.password, body.email)
    except passwords.PasswordError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _, token = await create_session(
        db, user, _client_ip(request), request.headers.get("user-agent")
    )
    await audit(
        db,
        "user.register",
        actor=user,
        request=request,
        detail={"username": user.username, "role": user.role},
    )
    await db.commit()
    _set_session_cookie(response, token)
    return LoginResult(username=user.username, role=user.role)


class ChangePasswordBody(BaseModel):
    current_password: str | None = Field(default=None, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)


@router.post("/password/change", status_code=204, dependencies=[Depends(csrf_protect)])
async def change_password(
    body: ChangePasswordBody,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    settings = await passwords.get_auth_settings(db)
    if not settings.password_enabled:
        raise HTTPException(status_code=403, detail="password sign-in is turned off")

    # Someone who signed in with a passkey and has no password yet can set
    # one; anyone replacing an existing password must prove they know it.
    if user.password_hash:
        if not body.current_password:
            raise HTTPException(status_code=400, detail="enter your current password")
        if await passwords.authenticate(db, user.username, body.current_password) is None:
            await audit(
                db,
                "auth.failed",
                actor=user,
                request=request,
                detail={"reason": "wrong_current_password"},
            )
            await db.commit()
            raise HTTPException(status_code=401, detail="that current password is not right")

    try:
        await passwords.set_password(db, user, body.new_password)
    except passwords.PasswordError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await audit(db, "user.password_change", actor=user, request=request)
    await db.commit()
    return Response(status_code=204)
