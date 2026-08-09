from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Tenant, User


class LoginNotAllowed(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


async def get_default_tenant(db: AsyncSession) -> Tenant:
    tenant = (await db.execute(select(Tenant).order_by(Tenant.created_at))).scalars().first()
    if tenant is None:
        tenant = Tenant(name="default")
        db.add(tenant)
        await db.flush()
    return tenant


async def upsert_user_from_claims(db: AsyncSession, claims: dict[str, Any]) -> User:
    """Map an OIDC identity to a local user.

    Pocket ID controls who can authenticate at all, so unknown identities are
    auto-provisioned as members. Matching order: stored subject, then
    preferred_username, then email, so pre-created accounts link on first login.
    """
    settings = get_settings()
    subject = claims.get("sub")
    username = claims.get("preferred_username") or ""
    email = (claims.get("email") or "").lower() or None
    if not subject:
        raise LoginNotAllowed("id token has no subject")

    user = (await db.execute(select(User).where(User.oidc_subject == subject))).scalar_one_or_none()

    if user is None and username:
        user = (
            await db.execute(
                select(User).where(
                    func.lower(User.username) == username.lower(), User.oidc_subject.is_(None)
                )
            )
        ).scalar_one_or_none()
    if user is None and email:
        user = (
            await db.execute(
                select(User).where(func.lower(User.email) == email, User.oidc_subject.is_(None))
            )
        ).scalar_one_or_none()

    if user is None:
        tenant = await get_default_tenant(db)
        # Whoever signs in first owns the instance. Without this, an install
        # using only single sign-on and no bootstrap list produced a first
        # account with no admin rights and nobody able to grant them.
        first_user = (await db.execute(select(func.count(User.id)))).scalar_one() == 0
        is_admin = (
            first_user
            or username.lower() in settings.admin_usernames
            or (email or "") in settings.admin_emails
        )
        # Defaults are set explicitly: SQLAlchemy column defaults only apply at
        # INSERT, and the is_active check below runs before the flush.
        user = User(
            tenant_id=tenant.id,
            oidc_subject=subject,
            username=username or (email or subject),
            email=email,
            role="admin" if is_admin else "member",
            services=[],
            prefs={},
            api_enabled=False,
            is_active=True,
        )
        db.add(user)
        await db.flush()
        # Same reason as the password path: no handle, no profile address,
        # so nobody can click through to them or write to them.
        from app.social import handles

        await handles.assign(db, user, prefer=username or email)
    else:
        user.oidc_subject = subject
        if email and not user.email:
            user.email = email

    if not user.is_active:
        raise LoginNotAllowed("account disabled")

    user.last_login_at = datetime.now(UTC)
    await db.flush()
    return user
