"""Password authentication.

Argon2id hashes, no user enumeration, and a per-account attempt limiter.
Runs alongside OIDC; an admin can enable either method, or both, but never
neither."""

import logging
import re
import unicodedata
from datetime import UTC, datetime

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import get_default_tenant
from app.config import get_settings
from app.models import AuthSettings, User

logger = logging.getLogger("watchpile.passwords")

hasher = PasswordHasher()

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 200
MAX_ATTEMPTS = 8
ATTEMPT_WINDOW_SECONDS = 900

# Verifying against this costs the same as a real hash, so a missing
# account and a wrong password take the same time.
_DUMMY_HASH = hasher.hash("watchpile-dummy-password-for-timing")

USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,39}$")


class PasswordError(Exception):
    """Raised for anything a caller may show the user verbatim."""


def normalize(password: str) -> str:
    # NFKC so a password typed on another keyboard layout still matches.
    return unicodedata.normalize("NFKC", password)


def validate_password(password: str) -> str:
    password = normalize(password)
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordError(f"use at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise PasswordError("that password is too long")
    if password.strip() == "":
        raise PasswordError("that password is only whitespace")
    return password


def validate_username(username: str) -> str:
    username = username.strip()
    if not USERNAME_RE.match(username):
        raise PasswordError(
            "usernames are 2 to 40 characters: letters, digits, dot, dash, underscore"
        )
    return username


def hash_password(password: str) -> str:
    return hasher.hash(validate_password(password))


async def get_auth_settings(db: AsyncSession) -> AuthSettings:
    row = (await db.execute(select(AuthSettings))).scalars().first()
    if row is None:
        tenant = await get_default_tenant(db)
        row = AuthSettings(
            tenant_id=tenant.id,
            oidc_enabled=True,
            # Password sign-in turns itself on when there is no identity
            # server configured, so a fresh local install is usable.
            password_enabled=not get_settings().oidc_client_id,
            registration_open=False,
        )
        db.add(row)
        await db.flush()
    return row


async def _attempt_key(username: str) -> str:
    return f"login:{username.lower()}"


async def too_many_attempts(username: str) -> bool:
    try:
        from redis.asyncio import Redis

        redis = Redis.from_url(get_settings().redis_url)
        try:
            count = await redis.get(await _attempt_key(username))
            return count is not None and int(count) >= MAX_ATTEMPTS
        finally:
            await redis.aclose()
    except Exception:
        # A broken limiter must not lock everyone out of their own app.
        logger.warning("login limiter unavailable, allowing the attempt")
        return False


async def record_failure(username: str) -> None:
    try:
        from redis.asyncio import Redis

        redis = Redis.from_url(get_settings().redis_url)
        try:
            key = await _attempt_key(username)
            await redis.incr(key)
            await redis.expire(key, ATTEMPT_WINDOW_SECONDS)
        finally:
            await redis.aclose()
    except Exception:
        logger.warning("could not record a failed login attempt")


async def clear_failures(username: str) -> None:
    try:
        from redis.asyncio import Redis

        redis = Redis.from_url(get_settings().redis_url)
        try:
            await redis.delete(await _attempt_key(username))
        finally:
            await redis.aclose()
    except Exception:
        pass


async def authenticate(db: AsyncSession, username: str, password: str) -> User | None:
    """Return the user, or None for any failure. The caller must not tell
    the person which part was wrong."""
    settings = await get_auth_settings(db)
    if not settings.password_enabled:
        return None

    user = (
        await db.execute(select(User).where(func.lower(User.username) == username.strip().lower()))
    ).scalar_one_or_none()

    stored = user.password_hash if user and user.password_hash else _DUMMY_HASH
    try:
        hasher.verify(stored, normalize(password))
        verified = True
    except (VerificationError, InvalidHashError, ValueError, TypeError):
        verified = False

    if not verified or user is None or not user.password_hash:
        return None
    if not user.is_active:
        return None

    # Transparently upgrade the hash when argon2 parameters change.
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hasher.hash(normalize(password))
    user.last_login_at = datetime.now(UTC)
    await db.flush()
    return user


async def set_password(db: AsyncSession, user: User, password: str) -> None:
    user.password_hash = hash_password(password)
    await db.flush()


async def register(db: AsyncSession, username: str, password: str, email: str | None) -> User:
    settings = await get_auth_settings(db)
    # An empty instance always accepts its first account, whatever the
    # switches say. Registration is closed by default and the switch itself
    # lives behind an admin login, so honouring it here left a fresh install
    # with no way in at all: no account, and no way to make one. The very
    # first account is the setup step, not a registration.
    first_user = (await db.execute(select(func.count(User.id)))).scalar_one() == 0
    if not first_user and (not settings.password_enabled or not settings.registration_open):
        raise PasswordError("account creation is closed")
    username = validate_username(username)
    exists = (
        await db.execute(select(User).where(func.lower(User.username) == username.lower()))
    ).scalar_one_or_none()
    if exists is not None:
        raise PasswordError("that username is taken")

    tenant = await get_default_tenant(db)
    user = User(
        tenant_id=tenant.id,
        username=username,
        email=(email or "").strip().lower() or None,
        # Whoever sets up the install becomes its admin.
        role="admin" if first_user else "member",
        services=[],
        prefs={},
        api_enabled=False,
        is_active=True,
        password_hash=hash_password(password),
    )
    db.add(user)
    await db.flush()
    # A handle is the only address a profile has. Without one the person is
    # not clickable anywhere and cannot be messaged, so it is filled in from
    # their username rather than left for them to discover in Settings.
    from app.social import handles

    await handles.assign(db, user)
    await db.flush()
    return user
