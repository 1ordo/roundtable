import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import audit
from app.auth.deps import csrf_protect, require_admin
from app.auth.service import get_default_tenant
from app.config import get_settings
from app.db import get_db
from app.models import AuditLog, FeatureFlag, ImportBatch, QuotaUsage, User

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])


class AuditRow(BaseModel):
    id: str
    action: str
    actor_user_id: str | None
    # Who did it, in words rather than a uuid to copy and paste.
    actor: str | None = None
    # What happened, in a sentence anyone can read.
    summary: str = ""
    category: str = "other"
    object_type: str | None
    object_id: str | None
    ip: str | None
    detail: dict | None
    created_at: datetime


class AuditPage(BaseModel):
    total: int
    rows: list[AuditRow]
    # Every action present in the log, for the filter.
    actions: list[str] = []


# How each action reads, and which group it belongs to.
ACTION_TEXT: dict[str, tuple[str, str]] = {
    "auth.login": ("signed in", "auth"),
    "auth.logout": ("signed out", "auth"),
    "auth.failed": ("failed to sign in", "auth"),
    "auth.denied": ("was refused sign-in", "auth"),
    "user.register": ("created an account", "auth"),
    "user.password_change": ("changed their password", "auth"),
    "user.password_set": ("set someone's password", "admin"),
    "user.create": ("created an account", "admin"),
    "user.update": ("changed an account", "admin"),
    "user.update_profile": ("updated their profile", "profile"),
    "user.avatar_update": ("changed their picture", "profile"),
    "settings.auth_update": ("changed the sign-in methods", "admin"),
    "settings.ai_update": ("changed the AI settings", "admin"),
    "flags.update": ("switched a feature flag", "admin"),
    "token.create": ("created an API token", "api"),
    "token.revoke": ("revoked an API token", "api"),
    "token.use": ("used an API token", "api"),
    "export.lists": ("exported their lists", "data"),
    "export.history": ("exported their history", "data"),
    "export.all": ("exported everything", "data"),
    "import.create": ("started an import", "data"),
    "import.extension": ("imported a list from the extension", "data"),
    "list.bulk_add": ("saved a whole franchise", "data"),
    "collection.watched": ("marked a franchise watched", "data"),
    "episodes.season": ("marked a season watched", "data"),
    "comment.create": ("wrote a comment", "social"),
    "post.create": ("posted", "social"),
    "quote.add": ("saved a quote", "social"),
    "comment.delete": ("deleted a comment", "social"),
    "friend.request": ("asked to be friends", "social"),
    "friend.accept": ("accepted a friend request", "social"),
    "friend.remove": ("removed a friend", "social"),
    "catalog.sweep": ("ran a catalog sweep", "admin"),
}


def _describe(row: AuditLog, actor: str | None) -> tuple[str, str]:
    """One readable sentence, plus the group it belongs to."""
    phrase, category = ACTION_TEXT.get(row.action, (row.action.replace(".", " "), "other"))
    who = actor or "someone"
    detail = row.detail or {}

    extra = ""
    if row.action == "auth.failed" and detail.get("reason"):
        reasons = {
            "bad_credentials": "wrong username or password",
            "rate_limited": "too many attempts",
            "wrong_current_password": "wrong current password",
            "oidc_error": "the identity server refused it",
        }
        extra = f" ({reasons.get(detail['reason'], detail['reason'])})"
        if detail.get("username"):
            who = detail["username"]
    elif row.action == "auth.login" and detail.get("method"):
        extra = f" with a {detail['method']}"
    elif row.action == "user.update" and detail:
        changes = ", ".join(f"{k} to {v}" for k, v in detail.items())
        extra = f": {changes}"
    elif row.action == "user.update_profile" and detail:
        extra = ": " + ", ".join(detail.keys())
    elif row.action == "settings.auth_update":
        on = [name for name in ("oidc", "password") if detail.get(name)]
        extra = f": {', '.join(on) or 'nothing'} enabled"
    elif row.action == "list.bulk_add" and detail.get("added") is not None:
        extra = f": {detail['added']} saved"
    elif row.action == "catalog.sweep" and detail.get("added") is not None:
        extra = f": {detail['added']} new titles"

    return f"{who} {phrase}{extra}", category


@router.get("/audit", response_model=AuditPage)
async def list_audit(
    db: AsyncSession = Depends(get_db),
    action: str | None = None,
    category: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
) -> AuditPage:
    query = select(AuditLog).order_by(AuditLog.created_at.desc())
    count_query = select(func.count(AuditLog.id))
    if action:
        query = query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)
    if category:
        wanted = [a for a, (_, group) in ACTION_TEXT.items() if group == category]
        query = query.where(AuditLog.action.in_(wanted))
        count_query = count_query.where(AuditLog.action.in_(wanted))
    total = (await db.execute(count_query)).scalar_one()
    rows = (await db.execute(query.limit(limit).offset(offset))).scalars().all()
    name_rows = (await db.execute(select(User.id, User.username))).all()
    names: dict[uuid.UUID, str] = {row[0]: row[1] for row in name_rows}
    actions = sorted((await db.execute(select(AuditLog.action).distinct())).scalars().all())
    return _audit_page(total, rows, names, actions)


class QuotaDay(BaseModel):
    day: date
    source: str
    count: int


class QuotaResponse(BaseModel):
    today: dict[str, int]
    omdb_daily_budget: int
    tmdb_configured: bool
    omdb_configured: bool
    last_30_days: list[QuotaDay]


@router.get("/quota", response_model=QuotaResponse)
async def quota_view(db: AsyncSession = Depends(get_db)) -> QuotaResponse:
    settings = get_settings()
    since = datetime.now(UTC).date() - timedelta(days=30)
    rows = (
        (
            await db.execute(
                select(QuotaUsage)
                .where(QuotaUsage.day >= since)
                .order_by(QuotaUsage.day.desc(), QuotaUsage.source)
            )
        )
        .scalars()
        .all()
    )
    today = datetime.now(UTC).date()
    return QuotaResponse(
        today={r.source: r.count for r in rows if r.day == today},
        omdb_daily_budget=settings.omdb_daily_budget,
        tmdb_configured=settings.tmdb_configured,
        omdb_configured=bool(settings.omdb_api_key),
        last_30_days=[QuotaDay(day=r.day, source=r.source, count=r.count) for r in rows],
    )


def _audit_page(
    total: int, rows, names: dict | None = None, actions: list[str] | None = None
) -> "AuditPage":
    names = names or {}
    out = []
    for r in rows:
        actor = names.get(r.actor_user_id)
        summary, category = _describe(r, actor)
        out.append(
            AuditRow(
                id=str(r.id),
                action=r.action,
                actor_user_id=str(r.actor_user_id) if r.actor_user_id else None,
                actor=actor,
                summary=summary,
                category=category,
                object_type=r.object_type,
                object_id=r.object_id,
                ip=r.ip,
                detail=r.detail,
                created_at=r.created_at,
            )
        )
    return AuditPage(total=total, rows=out, actions=actions or [])


class AdminUser(BaseModel):
    id: str
    username: str
    email: str | None
    role: str
    is_active: bool
    api_enabled: bool
    country_code: str | None
    last_login_at: datetime | None
    has_oidc: bool


def _admin_user(user: User) -> AdminUser:
    return AdminUser(
        id=str(user.id),
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        api_enabled=user.api_enabled,
        country_code=user.country_code,
        last_login_at=user.last_login_at,
        has_oidc=user.oidc_subject is not None,
    )


@router.get("/users", response_model=list[AdminUser])
async def list_users(db: AsyncSession = Depends(get_db)) -> list[AdminUser]:
    users = (await db.execute(select(User).order_by(User.created_at))).scalars().all()
    return [_admin_user(u) for u in users]


class CreateUserBody(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=255)
    role: str = Field(default="member", pattern="^(admin|member)$")


@router.post(
    "/users", response_model=AdminUser, status_code=201, dependencies=[Depends(csrf_protect)]
)
async def create_user(
    body: CreateUserBody,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    """Pre-provision an account; it links to Pocket ID on first login by
    username or email."""
    existing = (
        await db.execute(
            select(User).where(func.lower(User.username) == body.username.strip().lower())
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="username already exists")
    tenant = await get_default_tenant(db)
    user = User(
        tenant_id=tenant.id,
        username=body.username.strip(),
        email=(body.email or "").strip().lower() or None,
        role=body.role,
        services=[],
        prefs={},
        api_enabled=False,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await audit(
        db,
        "user.create",
        actor=admin,
        request=request,
        object_type="user",
        object_id=str(user.id),
        detail={"username": user.username},
    )
    await db.commit()
    return _admin_user(user)


class UpdateUserBody(BaseModel):
    is_active: bool | None = None
    role: str | None = Field(default=None, pattern="^(admin|member)$")
    api_enabled: bool | None = None


@router.patch("/users/{user_id}", response_model=AdminUser, dependencies=[Depends(csrf_protect)])
async def update_user(
    user_id: str,
    body: UpdateUserBody,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    try:
        uid = uuid.UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="user not found") from exc
    user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    if user.id == admin.id and body.is_active is False:
        raise HTTPException(status_code=400, detail="you cannot disable your own account")
    if user.id == admin.id and body.role == "member":
        raise HTTPException(status_code=400, detail="you cannot demote your own account")

    changes: dict = {}
    if body.is_active is not None:
        user.is_active = body.is_active
        changes["is_active"] = body.is_active
    if body.role is not None:
        user.role = body.role
        changes["role"] = body.role
    if body.api_enabled is not None:
        user.api_enabled = body.api_enabled
        changes["api_enabled"] = body.api_enabled
    if changes:
        await audit(
            db,
            "user.update",
            actor=admin,
            request=request,
            object_type="user",
            object_id=str(user.id),
            detail=changes,
        )
    await db.commit()
    return _admin_user(user)


class FlagOut(BaseModel):
    key: str
    enabled: bool
    description: str


KNOWN_FLAGS = {
    "api_tokens": "Allow members to create personal API tokens (per-user switch still applies)",
}


@router.get("/flags", response_model=list[FlagOut])
async def list_flags(db: AsyncSession = Depends(get_db)) -> list[FlagOut]:
    rows = {f.key: f for f in (await db.execute(select(FeatureFlag))).scalars().all()}
    out = []
    for key, description in KNOWN_FLAGS.items():
        row = rows.get(key)
        out.append(FlagOut(key=key, enabled=bool(row and row.enabled), description=description))
    return out


class FlagBody(BaseModel):
    enabled: bool


@router.put("/flags/{key}", response_model=FlagOut, dependencies=[Depends(csrf_protect)])
async def set_flag(
    key: str,
    body: FlagBody,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> FlagOut:
    if key not in KNOWN_FLAGS:
        raise HTTPException(status_code=404, detail="unknown flag")
    row = (await db.execute(select(FeatureFlag).where(FeatureFlag.key == key))).scalar_one_or_none()
    if row is None:
        row = FeatureFlag(key=key, enabled=body.enabled)
        db.add(row)
    else:
        row.enabled = body.enabled
    await audit(
        db,
        "flags.update",
        actor=admin,
        request=request,
        object_type="feature_flag",
        object_id=key,
        detail={"enabled": body.enabled},
    )
    await db.commit()
    return FlagOut(key=key, enabled=row.enabled, description=KNOWN_FLAGS[key])


class AdminImportRow(BaseModel):
    id: str
    username: str
    service: str
    status: str
    stats: dict
    created_at: datetime


@router.get("/imports", response_model=list[AdminImportRow])
async def all_imports(db: AsyncSession = Depends(get_db)) -> list[AdminImportRow]:
    rows = (
        await db.execute(
            select(ImportBatch, User.username)
            .join(User, User.id == ImportBatch.user_id)
            .order_by(ImportBatch.created_at.desc())
            .limit(100)
        )
    ).all()
    return [
        AdminImportRow(
            id=str(batch.id),
            username=username,
            service=batch.service,
            status=batch.status,
            stats=batch.stats or {},
            created_at=batch.created_at,
        )
        for batch, username in rows
    ]


class AuthSettingsOut(BaseModel):
    oidc_enabled: bool
    password_enabled: bool
    registration_open: bool
    oidc_configured: bool


@router.get("/settings/auth", response_model=AuthSettingsOut)
async def get_auth_settings_admin(db: AsyncSession = Depends(get_db)) -> AuthSettingsOut:
    from app.auth import passwords

    row = await passwords.get_auth_settings(db)
    await db.commit()
    return AuthSettingsOut(
        oidc_enabled=row.oidc_enabled,
        password_enabled=row.password_enabled,
        registration_open=row.registration_open,
        oidc_configured=bool(get_settings().oidc_client_id),
    )


class AuthSettingsBody(BaseModel):
    oidc_enabled: bool
    password_enabled: bool
    registration_open: bool = False


@router.put("/settings/auth", response_model=AuthSettingsOut, dependencies=[Depends(csrf_protect)])
async def update_auth_settings(
    body: AuthSettingsBody,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AuthSettingsOut:
    from app.auth import passwords

    if not body.oidc_enabled and not body.password_enabled:
        raise HTTPException(
            status_code=400,
            detail="keep at least one sign-in method on, or nobody can get back in",
        )
    # Guard against an admin turning off the only method they can use.
    if body.password_enabled and not admin.password_hash and not body.oidc_enabled:
        raise HTTPException(
            status_code=400,
            detail="set your own password first, otherwise you would lock yourself out",
        )

    row = await passwords.get_auth_settings(db)
    row.oidc_enabled = body.oidc_enabled
    row.password_enabled = body.password_enabled
    row.registration_open = body.registration_open and body.password_enabled
    await audit(
        db,
        "settings.auth_update",
        actor=admin,
        request=request,
        detail={
            "oidc": row.oidc_enabled,
            "password": row.password_enabled,
            "registration_open": row.registration_open,
        },
    )
    await db.commit()
    return AuthSettingsOut(
        oidc_enabled=row.oidc_enabled,
        password_enabled=row.password_enabled,
        registration_open=row.registration_open,
        oidc_configured=bool(get_settings().oidc_client_id),
    )


class SetPasswordBody(BaseModel):
    password: str = Field(min_length=1, max_length=200)


@router.put("/users/{user_id}/password", status_code=204, dependencies=[Depends(csrf_protect)])
async def set_user_password(
    user_id: str,
    body: SetPasswordBody,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    from app.auth import passwords

    try:
        uid = uuid.UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="user not found") from exc
    user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    try:
        await passwords.set_password(db, user, body.password)
    except passwords.PasswordError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await audit(
        db,
        "user.password_set",
        actor=admin,
        request=request,
        object_type="user",
        object_id=str(user.id),
    )
    await db.commit()


class CatalogStatus(BaseModel):
    titles: int
    indexed: int
    unindexed: int
    stale: int
    pages_done: int
    pages_total: int
    cursor: dict


@router.get("/catalog", response_model=CatalogStatus)
async def catalog_status(db: AsyncSession = Depends(get_db)) -> CatalogStatus:
    """How far the continuous catalog sweep has got."""
    from app.catalog import crawler

    return CatalogStatus(**await crawler.status(db))


@router.post("/catalog/sweep", dependencies=[Depends(csrf_protect)])
async def run_sweep(
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    pages: int = Query(default=2, ge=1, le=10),
) -> dict:
    """Take the next pages now rather than waiting for the schedule."""
    from app.catalog import crawler

    result = await crawler.sweep(db, pages_per_type=pages)
    await audit(db, "catalog.sweep", actor=admin, request=request, detail=result)
    await db.commit()
    return result
