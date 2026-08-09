"""The ledger: a word when a paid service goes a month unused.

Attribution is by catalog — a service counts as used when something watched
recently streams on it in the person's country — so every logging path
counts, not only plays the extension saw.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import Availability, Notification, Title, User, WatchEvent
from app.tracking import expenses

from .util import do_login


async def sign_in(client, fake_idp, name: str) -> str:
    await do_login(client, fake_idp, {"sub": f"sub-{name}", "preferred_username": name})
    return (await client.get("/api/me")).json()["csrf"]


async def _subscriber(db_session, client, fake_idp, name: str) -> tuple[User, str]:
    """A Netflix subscriber in Egypt whose account is old enough to judge."""
    csrf = await sign_in(client, fake_idp, name)
    user = (await db_session.execute(select(User).where(User.username == name))).scalar_one()
    user.services = [8]
    user.country_code = "EG"
    user.created_at = datetime.now(UTC) - timedelta(days=90)
    await db_session.commit()
    return user, csrf


async def _watched_netflix_title(db_session, user: User, days_ago: int) -> Title:
    title = Title(tmdb_id=354912, type="movie", name="Coco", genres=[])
    db_session.add(title)
    await db_session.flush()
    db_session.add(
        Availability(
            title_id=title.id,
            country="EG",
            provider_id=8,
            provider_name="Netflix",
            kind="stream",
        )
    )
    db_session.add(
        WatchEvent(
            user_id=user.id,
            title_id=title.id,
            watched_at=datetime.now(UTC) - timedelta(days=days_ago),
        )
    )
    await db_session.commit()
    return title


async def test_a_recent_watch_keeps_a_service_off_the_list(client, fake_idp, db_session):
    user, _ = await _subscriber(db_session, client, fake_idp, "meg")
    await _watched_netflix_title(db_session, user, days_ago=5)
    assert await expenses.idle_services(db_session, user) == []


async def test_a_quiet_month_puts_a_service_on_the_list(client, fake_idp, db_session):
    user, _ = await _subscriber(db_session, client, fake_idp, "ned")
    await _watched_netflix_title(db_session, user, days_ago=40)
    idle = await expenses.idle_services(db_session, user)
    assert [s["name"] for s in idle] == ["Netflix"]
    assert idle[0]["days_idle"] == 40


async def test_new_accounts_are_left_alone(client, fake_idp, db_session):
    user, _ = await _subscriber(db_session, client, fake_idp, "oli")
    user.created_at = datetime.now(UTC) - timedelta(days=5)
    await db_session.commit()
    assert await expenses.idle_services(db_session, user) == []


async def test_the_endpoint_stays_silent_until_asked(client, fake_idp, db_session):
    user, csrf = await _subscriber(db_session, client, fake_idp, "pia")
    await _watched_netflix_title(db_session, user, days_ago=40)

    body = (await client.get("/api/services/idle")).json()
    assert body == {"enabled": False, "services": []}

    saved = await client.put(
        "/api/me", json={"expense_alerts": True}, headers={"X-CSRF-Token": csrf}
    )
    assert saved.status_code == 200
    body = (await client.get("/api/services/idle")).json()
    assert body["enabled"] is True
    assert [s["name"] for s in body["services"]] == ["Netflix"]


async def test_one_reminder_per_cycle(client, fake_idp, db_session):
    user, csrf = await _subscriber(db_session, client, fake_idp, "rui")
    await _watched_netflix_title(db_session, user, days_ago=40)
    await client.put("/api/me", json={"expense_alerts": True}, headers={"X-CSRF-Token": csrf})
    await db_session.refresh(user)

    first = await expenses.remind_idle_services(db_session)
    await db_session.commit()
    assert first == {"reminded": 1}

    # The next daily pass says nothing: once per cycle, not per day.
    second = await expenses.remind_idle_services(db_session)
    await db_session.commit()
    assert second == {"reminded": 0}

    notes = (
        (
            await db_session.execute(
                select(Notification).where(
                    Notification.user_id == user.id, Notification.kind == "expenses"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(notes) == 1
    assert "Netflix" in notes[0].message
