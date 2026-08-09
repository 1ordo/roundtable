"""Reminders for subscriptions that earned nothing this month.

A service counts as used when something watched recently is on it in the
person's country: attribution by catalog rather than by player, so a watch
logged by hand counts exactly like one the extension saw. The whole feature
is opt-in — it is a suggestion about money, not an alert about film — and
when it does speak, it speaks about one service at most once per cycle.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.services import BY_ID
from app.models import Availability, Notification, User, WatchEvent

# A month of silence before anything is said, and a cooldown well past a
# month so one lapsed service produces one word per billing cycle, not a
# drumbeat.
IDLE_DAYS = 30
REMIND_EVERY_DAYS = 45

KIND = "expenses"


def enabled(user: User) -> bool:
    """Off unless asked for: money nudges are opted into, never defaulted."""
    return bool((user.prefs or {}).get("expense_alerts"))


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


async def idle_services(
    db: AsyncSession, user: User, days: int = IDLE_DAYS
) -> list[dict[str, Any]]:
    """Subscribed services with no watch on them for `days`.

    Availability rows carry raw TMDB provider ids, so each subscribed
    service is matched through its whole umbrella of regional ids.
    """
    if not user.services or not user.country_code:
        return []
    now = datetime.now(UTC)
    # A fresh account has an empty month behind it by definition; saying so
    # would be noise, not insight.
    if user.created_at is None or _aware(user.created_at) > now - timedelta(days=days):
        return []

    umbrella: dict[int, int] = {}
    for canonical in user.services:
        service = BY_ID.get(canonical)
        for sub in (service or {}).get("ids", [canonical]):
            umbrella[sub] = canonical

    rows = (
        await db.execute(
            select(Availability.provider_id, func.max(WatchEvent.watched_at))
            .join(WatchEvent, WatchEvent.title_id == Availability.title_id)
            .where(
                WatchEvent.user_id == user.id,
                Availability.country == user.country_code,
                Availability.provider_id.in_(list(umbrella)),
            )
            .group_by(Availability.provider_id)
        )
    ).all()
    last_used: dict[int, datetime] = {}
    for provider_id, seen in rows:
        canonical = umbrella[provider_id]
        seen = _aware(seen)
        if canonical not in last_used or seen > last_used[canonical]:
            last_used[canonical] = seen

    idle: list[dict[str, Any]] = []
    for canonical in user.services:
        service = BY_ID.get(canonical)
        if service is None:
            continue
        seen = last_used.get(canonical)
        if seen is not None and seen > now - timedelta(days=days):
            continue
        idle.append(
            {
                "id": canonical,
                "name": service["name"],
                "color": service.get("color"),
                "last_used": seen.date().isoformat() if seen else None,
                "days_idle": min((now - seen).days, 999) if seen else days,
            }
        )
    return idle


async def _already_told(db: AsyncSession, user_id: uuid.UUID, service_id: int) -> bool:
    since = datetime.now(UTC) - timedelta(days=REMIND_EVERY_DAYS)
    rows = (
        (
            await db.execute(
                select(Notification).where(
                    Notification.user_id == user_id,
                    Notification.kind == KIND,
                    Notification.created_at >= since,
                )
            )
        )
        .scalars()
        .all()
    )
    return any((n.payload or {}).get("service_id") == service_id for n in rows)


async def remind_idle_services(db: AsyncSession) -> dict[str, int]:
    """The daily pass: one inbox row per lapsed service per cycle.

    Writes the row directly rather than through notify(): this kind has its
    own opt-in, so a customised notify_kinds list must not silently mute a
    reminder the person explicitly asked for.
    """
    from app.notifications import ntfy

    users = (await db.execute(select(User).where(User.is_active.is_(True)))).scalars().all()
    reminded = 0
    for user in users:
        if not enabled(user):
            continue
        for service in await idle_services(db, user):
            if await _already_told(db, user.id, service["id"]):
                continue
            message = (
                f"A month with nothing watched on {service['name']}. "
                "If you are not using it, pausing it is free."
            )
            sent_via = ["inbox"]
            if await ntfy.push(user, "Roundtable", message):
                sent_via.append("ntfy")
            db.add(
                Notification(
                    user_id=user.id,
                    kind=KIND,
                    message=message,
                    payload={"service_id": service["id"], "href": "/app/settings"},
                    sent_via=sent_via,
                )
            )
            reminded += 1
    await db.flush()
    return {"reminded": reminded}
