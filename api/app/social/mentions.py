"""Telling someone that something happened to their post.

One place, so every social action notifies the same way and none of them
notify you about your own doing."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


def name_of(user: User) -> str:
    return user.display_name or (f"@{user.handle}" if user.handle else user.username)


async def tell(
    db: AsyncSession,
    actor: User,
    recipient_id: uuid.UUID,
    what: str,
    context: str = "",
    kind: str = "social",
) -> None:
    """Raise an inbox row, unless the actor is the recipient.

    Nobody wants to be told they liked their own post, and an app that does
    it looks broken rather than attentive."""
    if actor.id == recipient_id:
        return
    recipient = (await db.execute(select(User).where(User.id == recipient_id))).scalar_one_or_none()
    if recipient is None or not recipient.is_active:
        return

    from app.notifications import service as notifications

    snippet = context.strip().replace("\n", " ")
    if len(snippet) > 90:
        snippet = snippet[:90].rstrip() + "..."
    message = f"{name_of(actor)} {what}"
    if snippet:
        message += f': "{snippet}"'

    await notifications.notify(
        db,
        recipient,
        kind,
        message,
        payload={"from": actor.handle or actor.username, "what": what},
        push_title="Watchpile",
    )
