"""Handles people choose for themselves.

Sanitising is the whole job here. A handle appears in URLs, in mentions and
next to everything someone writes, so it has to be predictable, unambiguous
and impossible to use for impersonation or injection."""

import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User

MIN_LENGTH = 3
MAX_LENGTH = 24

# Names that would be confusing or would collide with a route.
RESERVED = {
    "admin",
    "administrator",
    "api",
    "app",
    "auth",
    "everyone",
    "help",
    "login",
    "logout",
    "me",
    "moderator",
    "new",
    "official",
    "root",
    "settings",
    "staff",
    "support",
    "system",
    "roundtable",
}

_ALLOWED = re.compile(r"^[a-z0-9_]+$")
# Characters that read as a Latin letter but are not one. Without this,
# someone can register a handle that looks identical to another person's.
_CONFUSABLE = re.compile(r"[^\x00-\x7F]")


class HandleError(ValueError):
    """The handle cannot be used, with a reason worth showing someone."""


def clean(raw: str) -> str:
    """The canonical form of a handle, or an error explaining why not.

    Deliberately strict rather than forgiving: silently rewriting someone's
    input into something they did not type is how people end up with a
    handle they did not choose."""
    value = (raw or "").strip().lstrip("@").lower()
    if not value:
        raise HandleError("pick a handle")
    if _CONFUSABLE.search(value):
        raise HandleError("use letters a to z, numbers and underscores only")
    if len(value) < MIN_LENGTH:
        raise HandleError(f"at least {MIN_LENGTH} characters")
    if len(value) > MAX_LENGTH:
        raise HandleError(f"at most {MAX_LENGTH} characters")
    if not _ALLOWED.match(value):
        raise HandleError("use letters a to z, numbers and underscores only")
    if value.startswith("_") or value.endswith("_"):
        raise HandleError("cannot start or end with an underscore")
    if "__" in value:
        raise HandleError("no double underscores")
    if value[0].isdigit():
        raise HandleError("start with a letter")
    if value in RESERVED:
        raise HandleError("that one is reserved")
    return value


async def is_free(db: AsyncSession, handle: str, exclude: User | None = None) -> bool:
    query = select(func.count(User.id)).where(User.handle == handle)
    if exclude is not None:
        query = query.where(User.id != exclude.id)
    return (await db.execute(query)).scalar_one() == 0


async def claim(db: AsyncSession, user: User, raw: str) -> str:
    """Validate and take a handle, or explain why it cannot be taken."""
    value = clean(raw)
    if not await is_free(db, value, exclude=user):
        raise HandleError("that one is taken")
    user.handle = value
    return value


def _seed_from(name: str) -> str:
    """A legal handle stem from whatever a person signed up as.

    Deliberately forgiving where `clean` is strict: this runs on a name the
    person did not choose as a handle, so mangling it into something legal
    is the point, and they can change it afterwards.
    """
    value = (name or "").strip().lstrip("@").lower()
    value = value.split("@")[0]  # an email address is a fine starting point
    value = re.sub(r"[^a-z0-9_]+", "_", value).strip("_")
    value = re.sub(r"_+", "_", value)
    value = re.sub(r"^[^a-z]+", "", value)  # must start with a letter
    return value[:MAX_LENGTH].rstrip("_")


async def assign(db: AsyncSession, user: User, prefer: str | None = None) -> str | None:
    """Give someone a handle if they have none, without asking.

    A handle is the only address a profile has: no handle means no profile
    URL, which means the person is not clickable anywhere in the app, cannot
    be messaged, and cannot be linked to from a post. Leaving it optional
    made that the default state of every new account.

    Still theirs to change in Settings. This only fills the gap.
    """
    if user.handle:
        return user.handle
    stem = _seed_from(prefer or user.username or (user.email or ""))
    if len(stem) < MIN_LENGTH:
        stem = f"{stem}_watcher" if stem else "watcher"
        stem = stem[:MAX_LENGTH]
    if stem in RESERVED:
        stem = f"{stem}_1"[:MAX_LENGTH]

    candidate = stem
    for suffix in range(2, 200):
        try:
            value = clean(candidate)
        except HandleError:
            return None  # nothing legal to be made of it; Settings can fix it
        if await is_free(db, value, exclude=user):
            user.handle = value
            return value
        tail = f"_{suffix}"
        candidate = stem[: MAX_LENGTH - len(tail)] + tail
    return None
