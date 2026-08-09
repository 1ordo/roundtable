"""List plumbing shared by the API routes and the import pipeline."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import List, ListItem, User

SHARED_LIST_NAME = "Our list"


async def ensure_watchlist(db: AsyncSession, user: User) -> List:
    row = (
        await db.execute(select(List).where(List.user_id == user.id, List.kind == "watchlist"))
    ).scalar_one_or_none()
    if row is None:
        row = List(tenant_id=user.tenant_id, user_id=user.id, name="Watchlist", kind="watchlist")
        db.add(row)
        await db.flush()
    return row


async def ensure_shared_list(db: AsyncSession, user: User) -> List:
    row = (
        await db.execute(
            select(List).where(List.tenant_id == user.tenant_id, List.kind == "shared")
        )
    ).scalar_one_or_none()
    if row is None:
        row = List(tenant_id=user.tenant_id, user_id=None, name=SHARED_LIST_NAME, kind="shared")
        db.add(row)
        await db.flush()
    return row


# Lists the app makes for its own bookkeeping. They belong to the user, but
# they are not lists the user made, so they do not belong on My lists where
# they show up as an unnamed card that cannot be deleted.
INTERNAL_KINDS = ("cinema",)


async def visible_lists(db: AsyncSession, user: User, include_internal: bool = False) -> list[List]:
    await ensure_watchlist(db, user)
    await ensure_shared_list(db, user)
    query = select(List).where(
        (List.user_id == user.id) | ((List.tenant_id == user.tenant_id) & (List.kind == "shared"))
    )
    if not include_internal:
        query = query.where(List.kind.not_in(INTERNAL_KINDS))
    rows = (await db.execute(query.order_by(List.created_at))).scalars()
    return list(rows)


def can_touch_list(user: User, lst: List) -> bool:
    if lst.kind == "shared":
        return lst.tenant_id == user.tenant_id
    return lst.user_id == user.id or user.role == "admin"


async def add_title_to_list(
    db: AsyncSession, lst: List, title_id, user: User, note: str | None = None
) -> ListItem:
    existing = (
        await db.execute(
            select(ListItem).where(ListItem.list_id == lst.id, ListItem.title_id == title_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        if note is not None:
            existing.note = note
        return existing
    item = ListItem(list_id=lst.id, title_id=title_id, added_by=user.id, note=note)
    db.add(item)
    # Saving is one of the four signals the product claims feeds your taste,
    # and it was the one that did not: the vector is built from watch events
    # and interactions, and a list item is neither. Recorded once, on the
    # first save, because re-adding something is not a second opinion.
    from app.models import Interaction

    db.add(Interaction(user_id=user.id, title_id=title_id, kind="save"))
    await db.flush()

    from app.ai import taste as taste_module

    await taste_module.invalidate_taste(db, user)
    return item
