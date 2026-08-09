"""Who can see whose things.

One module, because the alternative is each endpoint deciding for itself and
the answers drifting apart. A privacy setting that holds on the profile page
but leaks through the comments feed is worse than no setting at all.

Three levels, in the order people expect:

  public   anyone signed in to this instance
  friends  accepted friends only, and the default
  private  nobody but them

Nothing is visible to the open internet at any level. "Public" here means
public to the household and whoever they have invited, not to the world.
"""

import uuid
from collections.abc import Iterable

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Friendship, User

LEVELS = ("public", "friends", "private")
DEFAULT = "friends"

# The parts of a profile that carry a level of their own. Each one falls back
# to the account level when it has none, so someone can show their numbers to
# everybody and keep their lists among friends.
#
# "posts" governs written things wherever they appear, not only on the profile
# page: the feed, the comments under a title, and saved quotes. A setting that
# holds in one place and leaks in another is worse than no setting.
STAT_PANELS = ("numbers", "favourites", "lists", "posts", "genres")


async def friend_ids(db: AsyncSession, user: User) -> set[uuid.UUID]:
    """Accepted friendships only, in both directions."""
    rows = (
        await db.execute(
            select(Friendship).where(
                Friendship.status == "accepted",
                or_(
                    Friendship.requester_id == user.id,
                    Friendship.addressee_id == user.id,
                ),
            )
        )
    ).scalars()
    out: set[uuid.UUID] = set()
    for row in rows:
        out.add(row.addressee_id if row.requester_id == user.id else row.requester_id)
    return out


async def can_see(db: AsyncSession, viewer: User | None, subject: User) -> bool:
    """Whether viewer may see subject's lists, history, stats and comments."""
    if viewer is not None and viewer.id == subject.id:
        return True  # your own things, always
    level = subject.visibility or DEFAULT
    if level == "private":
        return False
    if viewer is None:
        return False  # signed out sees nothing, whatever the setting
    if level == "public":
        return True
    return subject.id in await friend_ids(db, viewer)


async def visible_user_ids(db: AsyncSession, viewer: User) -> set[uuid.UUID]:
    """Everyone whose things this viewer may see, themselves included.

    Computed once per request and passed down, rather than asking per row:
    a feed of fifty comments would otherwise run fifty friendship queries.

    Being someone's friend is not by itself enough. A friend who has set
    themselves to private is still private, to friends most of all, so the
    friend set is filtered by the setting rather than trusted."""
    friends = await friend_ids(db, viewer)
    open_friends = set()
    if friends:
        open_friends = set(
            (
                await db.execute(
                    select(User.id).where(
                        User.id.in_(friends),
                        User.visibility != "private",
                        User.is_active.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
    public = set(
        (
            await db.execute(
                select(User.id).where(
                    User.visibility == "public",
                    User.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    return {viewer.id} | open_friends | public


def filter_visible(rows: Iterable, allowed: set[uuid.UUID], key: str = "user_id") -> list:
    """Keep only rows whose author the viewer may see."""
    return [row for row in rows if getattr(row, key) in allowed]


def _level_for(account_level: str | None, prefs: dict | None, panel: str) -> str:
    """The level that governs one panel.

    The account level is the default rather than a ceiling, so someone whose
    profile is friends-only can still make one panel public without opening
    the rest.
    """
    chosen = (prefs or {}).get("panel_visibility") or {}
    value = chosen.get(panel)
    if value in LEVELS:
        return str(value)
    return account_level or DEFAULT


def panel_level(user: User, panel: str) -> str:
    """The level chosen for one panel, falling back to the profile's own."""
    return _level_for(user.visibility, user.prefs, panel)


async def can_see_panel(db: AsyncSession, viewer: User, subject: User, panel: str) -> bool:
    """Whether viewer may see one named panel of subject's profile."""
    if viewer.id == subject.id:
        return True  # your own things, always
    level = panel_level(subject, panel)
    if level == "private":
        return False
    if level == "public":
        return True
    return subject.id in await friend_ids(db, viewer)


async def visible_user_ids_for_panel(db: AsyncSession, viewer: User, panel: str) -> set[uuid.UUID]:
    """Everyone whose named panel this viewer may see, themselves included.

    The panel-aware sibling of visible_user_ids, and the one to reach for
    anywhere a list mixes several people's things. The account-level set is
    not a valid substitute: someone public who set their posts to private
    would still have every post shown.

    The level lives in a JSON column, so the decision is made here rather
    than in SQL. Only three columns are loaded, and the row set is the same
    one visible_user_ids already walks.
    """
    friends = await friend_ids(db, viewer)
    rows = (
        await db.execute(
            select(User.id, User.visibility, User.prefs).where(User.is_active.is_(True))
        )
    ).all()
    allowed = {viewer.id}
    for user_id, account_level, prefs in rows:
        if user_id == viewer.id:
            continue
        level = _level_for(account_level, prefs, panel)
        if level == "public" or (level == "friends" and user_id in friends):
            allowed.add(user_id)
    return allowed
