"""Local development sign-in.

Lets the app run on a laptop with no identity server. It is gated by two
settings that must both be set (WD_ENV=dev and WD_DEV_LOGIN=true) and the
app refuses to boot if they are set in a production environment."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import upsert_user_from_claims
from app.config import get_settings
from app.models import User

DEFAULT_DEV_USERS = ("Lordo", "Nadia")


class DevLoginNotAllowed(Exception):
    pass


def assert_safe_configuration() -> None:
    """Called at startup. A misconfigured deployment fails loudly here
    instead of quietly accepting passwordless logins."""
    settings = get_settings()
    if settings.dev_login and settings.env != "dev":
        raise RuntimeError(
            "WD_DEV_LOGIN is on but WD_ENV is not 'dev'. Refusing to start: "
            "development sign-in must never be reachable outside development."
        )


async def dev_login_user(db: AsyncSession, username: str | None) -> User:
    settings = get_settings()
    if not settings.dev_login_enabled:
        raise DevLoginNotAllowed("development sign-in is not enabled")
    name = (username or DEFAULT_DEV_USERS[0]).strip()[:120] or DEFAULT_DEV_USERS[0]
    # Same code path as a real login, so roles and bootstrap behave identically.
    return await upsert_user_from_claims(
        db,
        {
            "sub": f"dev:{name.lower()}",
            "preferred_username": name,
            "email": f"{name.lower()}@localhost",
        },
    )
