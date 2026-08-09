"""Availability poller: refresh watchlist titles, diff provider rows, and
notify the people who care."""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import ingest, tmdb
from app.models import Availability, Episode, List, ListItem, Notification, Title, User
from app.notifications import email, ntfy

logger = logging.getLogger("roundtable.notifications")

# The poller runs daily; a provider row not confirmed within this window has
# effectively disappeared, so its reappearance is worth announcing.
GONE_AFTER = timedelta(days=2)

KIND_LABEL = {
    "stream": "streaming",
    "rent": "for rent",
    "buy": "to buy",
    "ads": "free with ads",
    "free": "free",
}


async def _watchers_by_title(db: AsyncSession) -> dict[uuid.UUID, set[uuid.UUID]]:
    """title_id -> user ids who track it. Personal lists map to their owner;
    the shared list maps to every user in the tenant."""
    users = (await db.execute(select(User))).scalars().all()
    tenant_users: dict[uuid.UUID, list[User]] = {}
    for user in users:
        tenant_users.setdefault(user.tenant_id, []).append(user)

    watchers: dict[uuid.UUID, set[uuid.UUID]] = {}
    rows = (
        await db.execute(
            select(ListItem.title_id, List.user_id, List.kind, List.tenant_id).join(
                List, ListItem.list_id == List.id
            )
        )
    ).all()
    for title_id, owner_id, kind, tenant_id in rows:
        bucket = watchers.setdefault(title_id, set())
        if kind == "shared":
            bucket.update(u.id for u in tenant_users.get(tenant_id, []))
        elif owner_id is not None:
            bucket.add(owner_id)
    return watchers


def _relevant(user: User, country: str, provider_id: int) -> bool:
    """Whether one availability change is worth telling one person about.

    Every country they follow counts, not only the main one: someone with
    a life split across two places wants to hear about both."""
    from app.countries import for_user

    wanted = for_user(user)
    if not wanted:
        return False  # no country set: no availability alerts yet
    if country not in wanted:
        return False
    return not (user.services and provider_id not in user.services)


# Every kind that has a switch on the settings screen. Must match
# app.routers.profile.NOTIFY_KINDS.
KINDS = frozenset(
    {
        "availability",
        "franchise",
        "episode",
        "cinema",
        "person",
        "social",
        "message",
        "friend_request",
        "night_invite",
        "night_survey",
    }
)

# Keys the old settings screen offered that nothing ever emitted. Their
# presence in a saved list marks it as written before the kinds were fixed.
LEGACY_KINDS = frozenset({"like", "shared"})


def wants(user: User, kind: str) -> bool:
    """Alert kinds the person has switched off are never created at all,
    rather than created and hidden: an inbox that fills with things you
    muted is not muted.

    A kind with no switch is always sent. The saved list is an allowlist,
    and treating it as authoritative for kinds it was never able to contain
    is how touching the settings screen once used to mute friend requests,
    watch night invites, surveys, cinema alerts and direct messages
    permanently. A preference can only speak for the choices it was offered.
    """
    if kind not in KINDS:
        return True
    chosen = (user.prefs or {}).get("notify_kinds")
    if chosen is None:
        return True
    # A list saved by the old settings screen can only have come from the
    # four keys it offered, two of which were never real. Such a list says
    # nothing about the kinds it could not name, so it is treated as unset
    # rather than as a decision to mute them. Self-healing on read, because
    # the alternative is a data migration that guesses at intent.
    if set(chosen) & LEGACY_KINDS:
        return True
    return kind in chosen


async def notify(
    db: AsyncSession,
    user: User,
    kind: str,
    message: str,
    title: Title | None = None,
    payload: dict[str, Any] | None = None,
    push_title: str = "Roundtable",
    episode: "Episode | None" = None,
) -> Notification | None:
    if not wants(user, kind):
        return None
    sent_via = ["inbox"]
    if await ntfy.push(user, push_title, message):
        sent_via.append("ntfy")
    # Silent when there is no key or the person has not asked for email, so
    # an instance without it behaves exactly as it did before.
    if await email.send(db, user, push_title, message):
        sent_via.append("email")
    notification = Notification(
        user_id=user.id,
        kind=kind,
        title_id=title.id if title else None,
        episode_id=episode.id if episode else None,
        message=message,
        payload=payload or {},
        sent_via=sent_via,
    )
    db.add(notification)
    await db.flush()
    return notification


async def poll_availability(db: AsyncSession) -> dict[str, int]:
    """Refresh availability for every tracked title and notify on new provider
    appearances. Returns counters for logs and tests."""
    watchers = await _watchers_by_title(db)
    users_by_id = {u.id: u for u in (await db.execute(select(User))).scalars().all()}
    counters = {"titles": 0, "new_rows": 0, "notifications": 0}

    for title_id, watcher_ids in watchers.items():
        title = (await db.execute(select(Title).where(Title.id == title_id))).scalar_one_or_none()
        if title is None:
            continue

        # Remember when each provider row was last confirmed. A row whose
        # last_seen went stale and is now fresh again means the title came
        # back to that provider, which is just as notify-worthy as a first
        # appearance.
        before: dict[tuple, datetime] = {}
        for a in (
            await db.execute(select(Availability).where(Availability.title_id == title.id))
        ).scalars():
            seen = a.last_seen_at
            if seen.tzinfo is None:
                seen = seen.replace(tzinfo=UTC)
            before[(a.country, a.provider_id, a.kind)] = seen

        try:
            await ingest.ensure_title(db, title.type, title.tmdb_id, force=True)
        except (tmdb.TmdbError, tmdb.TmdbNotConfigured):
            logger.warning("availability refresh failed for %s", title.name)
            continue
        except httpx.HTTPError:
            # Timeouts and connection resets are expected on a long run;
            # skip this title rather than losing the whole poll.
            logger.warning("availability refresh timed out for %s", title.name)
            continue
        counters["titles"] += 1

        after_rows = (
            (await db.execute(select(Availability).where(Availability.title_id == title.id)))
            .scalars()
            .all()
        )
        cutoff = datetime.now(UTC) - GONE_AFTER
        new_rows = []
        for row in after_rows:
            key = (row.country, row.provider_id, row.kind)
            previous = before.get(key)
            if previous is None or previous < cutoff:
                new_rows.append(row)
        counters["new_rows"] += len(new_rows)

        for row in new_rows:
            for user_id in watcher_ids:
                user = users_by_id.get(user_id)
                if user is None or not _relevant(user, row.country, row.provider_id):
                    continue
                label = KIND_LABEL.get(row.kind, row.kind)
                message = f"{title.name} is now {label} on {row.provider_name} in {row.country}"
                made = await notify(
                    db,
                    user,
                    "availability",
                    message,
                    title=title,
                    payload={
                        "provider_name": row.provider_name,
                        "provider_id": row.provider_id,
                        "country": row.country,
                        "kind": row.kind,
                    },
                    push_title="New on your services",
                )
                # The counter tracks alerts actually raised, not attempts:
                # a muted kind returns None.
                counters["notifications"] += 1 if made else 0

        # Commit per title: a later failure must not roll back inbox rows
        # whose push notifications have already gone out.
        await db.commit()

    await db.commit()
    logger.info("availability poll: %s", counters)
    return counters


async def notify_new_franchise_parts(db: AsyncSession) -> dict:
    """Tell people when a franchise they enjoyed gets a new entry.

    Watching or liking one part is a standing interest in the rest, so a
    newly announced sequel is worth a word. Each part is announced once per
    person, which the notification rows themselves record."""
    from app.catalog import tmdb
    from app.models import Interaction, Notification, Title, User, WatchEvent

    counters = {"users": 0, "notifications": 0}
    users = (await db.execute(select(User).where(User.is_active.is_(True)))).scalars().all()

    for user in users:
        engaged = (
            (
                await db.execute(
                    select(Title)
                    .join(WatchEvent, WatchEvent.title_id == Title.id)
                    .where(WatchEvent.user_id == user.id, Title.collection_id.is_not(None))
                )
            )
            .scalars()
            .all()
        )
        liked = (
            (
                await db.execute(
                    select(Title)
                    .join(Interaction, Interaction.title_id == Title.id)
                    .where(
                        Interaction.user_id == user.id,
                        Interaction.kind == "like",
                        Title.collection_id.is_not(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        # The query already filters to titles that belong to one, so the id
        # is present; narrowing it here keeps that promise explicit.
        collections: dict[int, Title] = {
            t.collection_id: t for t in list(engaged) + list(liked) if t.collection_id is not None
        }
        if not collections:
            continue
        counters["users"] += 1

        already = {
            (n.payload or {}).get("tmdb_id")
            for n in (
                await db.execute(
                    select(Notification).where(
                        Notification.user_id == user.id, Notification.kind == "franchise"
                    )
                )
            ).scalars()
        }

        for collection_id, anchor in collections.items():
            try:
                payload = await tmdb.collection(db, collection_id)
            except (tmdb.TmdbNotConfigured, tmdb.TmdbError):
                continue
            known_ids = {
                t.tmdb_id
                for t in (
                    await db.execute(
                        select(Title).where(
                            Title.collection_id == collection_id, Title.type == "movie"
                        )
                    )
                ).scalars()
            }
            for part in payload.get("parts", []):
                part_id = part.get("id")
                if part_id in known_ids or part_id in already or not part.get("poster_path"):
                    continue
                name = part.get("title") or "A new part"
                year = (part.get("release_date") or "")[:4]
                message = (
                    f"{name}{f' ({year})' if year else ''} joins the "
                    f"{payload.get('name', 'franchise')}, after you enjoyed {anchor.name}"
                )
                made = await notify(
                    db,
                    user,
                    "franchise",
                    message,
                    payload={
                        "tmdb_id": part_id,
                        "type": "movie",
                        "collection": payload.get("name"),
                    },
                    push_title="New in a franchise you follow",
                )
                already.add(part_id)
                counters["notifications"] += 1 if made else 0
        await db.commit()

    logger.info("franchise watch: %s", counters)
    return counters


async def watch_followed_people(db: AsyncSession) -> dict[str, int]:
    """Tell people when someone they follow has something new out.

    "New" means a release year past the newest one already seen for that
    person when they were followed, so following someone with a long career
    does not produce an alert for every film they ever made."""
    from app.catalog import tmdb
    from app.models import FollowedPerson

    counters = {"people": 0, "notifications": 0}
    rows = (await db.execute(select(FollowedPerson))).scalars().all()
    users_by_id = {u.id: u for u in (await db.execute(select(User))).scalars().all()}
    this_year = datetime.now(UTC).year

    for row in rows:
        person = users_by_id.get(row.user_id)
        if person is None:
            continue
        try:
            payload = await tmdb.person(db, row.person_id)
        except (tmdb.TmdbNotConfigured, tmdb.TmdbError):
            continue
        counters["people"] += 1

        credits = (payload.get("combined_credits") or {}).get("cast") or []
        newest = row.last_seen_credit or 0
        for credit in credits:
            date = str(credit.get("release_date") or credit.get("first_air_date") or "")
            year_text = date[:4]
            if not year_text.isdigit():
                continue
            year = int(year_text)
            # Only things out now or already out: an announcement years away
            # is not news anyone can act on.
            if year <= newest or year > this_year:
                continue
            name = credit.get("title") or credit.get("name")
            if not name or not credit.get("poster_path"):
                continue
            made = await notify(
                db,
                person,
                "person",
                f"{row.name} is in {name} ({year})",
                payload={
                    "tmdb_id": credit.get("id"),
                    "type": "movie" if credit.get("title") else "tv",
                    "person_id": row.person_id,
                },
                push_title="Someone you follow",
            )
            counters["notifications"] += 1 if made else 0
            newest = max(newest, year)
        row.last_seen_credit = newest or None
        await db.commit()

    logger.info("followed people: %s", counters)
    return counters


async def notify_new_episodes(db: AsyncSession) -> dict:
    """Tell people when a show they are watching puts out a new episode.

    Who counts as watching a show: anyone who has logged at least one of its
    episodes and has not finished it, or anyone with it on a list. Watching
    one episode of something is a standing interest in the next one, and
    keeping a show on a list is the same statement made in advance.

    Only episodes that have actually aired are announced, one per person per
    episode, recorded by the notification's own episode_id rather than by a
    flag that a later run could reset. Episodes that aired before the person
    started following the show are not announced, because a back catalogue
    arriving as fifty alerts is not news, it is a flood.
    """
    from app.catalog import episodes as episodes_service

    counters = {"shows": 0, "notifications": 0}
    today = datetime.now(UTC).date()
    users = (await db.execute(select(User).where(User.is_active.is_(True)))).scalars().all()

    for user in users:
        if not wants(user, "episode"):
            continue

        # Shows they have episodes logged against, plus shows on their lists.
        from app.models import WatchEvent

        watched_shows = set(
            (
                await db.execute(
                    select(WatchEvent.title_id)
                    .join(Title, Title.id == WatchEvent.title_id)
                    .where(WatchEvent.user_id == user.id, Title.type == "tv")
                )
            )
            .scalars()
            .all()
        )
        listed_shows = set(
            (
                await db.execute(
                    select(ListItem.title_id)
                    .join(List, List.id == ListItem.list_id)
                    .join(Title, Title.id == ListItem.title_id)
                    .where(List.user_id == user.id, Title.type == "tv")
                )
            )
            .scalars()
            .all()
        )
        show_ids = watched_shows | listed_shows
        if not show_ids:
            continue

        for show_id in show_ids:
            show = (await db.execute(select(Title).where(Title.id == show_id))).scalar_one_or_none()
            if show is None:
                continue
            counters["shows"] += 1
            try:
                await episodes_service.sync_series(db, show)
            except Exception:  # noqa: BLE001 - one bad show must not stop the sweep
                logger.exception("episodes: sync failed for %s", show.name)
                continue

            # The clock starts when they began following the show, so the
            # back catalogue never arrives as a wall of notifications.
            since = (
                await db.execute(
                    select(func.min(WatchEvent.created_at)).where(
                        WatchEvent.user_id == user.id, WatchEvent.title_id == show.id
                    )
                )
            ).scalar_one_or_none()
            started = since.date() if since is not None else today

            fresh = (
                (
                    await db.execute(
                        select(Episode)
                        .where(
                            Episode.title_id == show.id,
                            Episode.air_date.is_not(None),
                            Episode.air_date <= today,
                            Episode.air_date >= started,
                            Episode.season_number != episodes_service.SPECIALS,
                        )
                        .order_by(Episode.season_number, Episode.episode_number)
                    )
                )
                .scalars()
                .all()
            )
            for episode in fresh:
                already = (
                    await db.execute(
                        select(Notification).where(
                            Notification.user_id == user.id,
                            Notification.episode_id == episode.id,
                            Notification.kind == "episode",
                        )
                    )
                ).scalar_one_or_none()
                if already is not None:
                    continue
                label = f"S{episode.season_number}E{episode.episode_number}"
                named = f" {episode.name}" if episode.name else ""
                made = await notify(
                    db,
                    user,
                    "episode",
                    f"{show.name} {label}{named} is out.",
                    title=show,
                    episode=episode,
                    payload={
                        "tmdb_id": show.tmdb_id,
                        "type": "tv",
                        "season": episode.season_number,
                        "episode": episode.episode_number,
                    },
                    push_title="New episode",
                )
                counters["notifications"] += 1 if made else 0
        await db.commit()

    logger.info("new episodes: %s", counters)
    return counters
