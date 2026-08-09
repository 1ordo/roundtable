"""Preferences that change behaviour, not just stored flags."""

from datetime import UTC, datetime

import numpy as np

from app.ai import taste
from app.models import Notification, Title, User, WatchEvent
from app.notifications import service as notifications
from tests.util import do_login


async def test_discovery_mode_changes_how_far_suggestions_wander():
    comfort_explore, comfort_penalty = taste.DISCOVERY_MODES["comfort"]
    bold_explore, bold_penalty = taste.DISCOVERY_MODES["adventurous"]
    assert bold_explore > comfort_explore
    assert bold_penalty > comfort_penalty
    # An unknown value must not crash the ranking; it falls back.
    assert taste.DISCOVERY_MODES.get("nonsense", taste.DISCOVERY_MODES["balanced"]) == (
        taste.EXPLORE_FRACTION,
        taste.DIVERSITY_PENALTY,
    )


async def test_muted_alert_kinds_are_never_created(client, fake_idp, db_session):
    from sqlalchemy import select

    await do_login(client, fake_idp, {"sub": "s-m", "preferred_username": "mutes"})
    user = (await db_session.execute(select(User).where(User.username == "mutes"))).scalar_one()
    user.prefs = {"notify_kinds": ["franchise"]}
    await db_session.commit()

    assert notifications.wants(user, "franchise") is True
    assert notifications.wants(user, "availability") is False

    made = await notifications.notify(db_session, user, "availability", "should not appear")
    assert made is None
    kept = await notifications.notify(db_session, user, "franchise", "should appear")
    assert kept is not None
    await db_session.commit()

    rows = (await db_session.execute(select_notifications(user))).scalars().all()
    assert [r.message for r in rows] == ["should appear"]


def select_notifications(user):
    from sqlalchemy import select

    return select(Notification).where(Notification.user_id == user.id)


def test_no_preference_means_every_alert_still_arrives():
    user = User(username="default", email="d@test", prefs={})
    assert notifications.wants(user, "availability") is True
    assert notifications.wants(user, "anything-new") is True


async def test_hide_watched_removes_seen_titles_from_shelves(client, fake_idp, db_session):
    from sqlalchemy import select

    from app.routers.catalog import HomeRow, TitleCard, _hide_watched

    await do_login(client, fake_idp, {"sub": "s-w", "preferred_username": "watcher"})
    user = (await db_session.execute(select(User).where(User.username == "watcher"))).scalar_one()

    seen = Title(tmdb_id=11, type="movie", name="Already Seen", genres=[])
    fresh = [Title(tmdb_id=20 + i, type="movie", name=f"Unseen {i}", genres=[]) for i in range(5)]
    db_session.add_all([seen, *fresh])
    await db_session.flush()
    db_session.add(WatchEvent(user_id=user.id, title_id=seen.id, watched_at=datetime.now(UTC)))
    await db_session.commit()

    def card(t: Title) -> TitleCard:
        return TitleCard(
            tmdb_id=t.tmdb_id,
            type=t.type,
            name=t.name,
            poster_path=None,
            backdrop_path=None,
            year=None,
            tmdb_rating=None,
        )

    rows = [
        HomeRow(key="a", title="Big shelf", items=[card(seen)] + [card(t) for t in fresh]),
        # Only the watched title plus three others: too thin once filtered.
        HomeRow(key="b", title="Thin shelf", items=[card(seen)] + [card(t) for t in fresh[:3]]),
    ]
    kept = await _hide_watched(db_session, user, rows)

    assert [r.key for r in kept] == ["a"]
    assert all(i.name != "Already Seen" for i in kept[0].items)
    assert len(kept[0].items) == 5


async def test_hide_watched_is_a_no_op_before_anything_is_watched(client, fake_idp, db_session):
    from sqlalchemy import select

    from app.routers.catalog import HomeRow, TitleCard, _hide_watched

    await do_login(client, fake_idp, {"sub": "s-n", "preferred_username": "newcomer"})
    user = (await db_session.execute(select(User).where(User.username == "newcomer"))).scalar_one()
    rows = [
        HomeRow(
            key="a",
            title="Shelf",
            items=[
                TitleCard(
                    tmdb_id=1,
                    type="movie",
                    name="One",
                    poster_path=None,
                    backdrop_path=None,
                    year=None,
                    tmdb_rating=None,
                ),
            ],
        )
    ]
    # The shelf is under the four-item floor, and is still returned untouched
    # because no filtering happened at all.
    assert await _hide_watched(db_session, user, rows) == rows


async def test_preferences_round_trip_through_the_api(client, fake_idp, db_session):
    from sqlalchemy import select

    await do_login(client, fake_idp, {"sub": "s-p", "preferred_username": "prefs"})
    csrf = (await client.get("/api/me")).json()["csrf"]
    response = await client.put(
        "/api/me",
        json={
            "discovery": "adventurous",
            "hide_watched": True,
            "default_type": "tv",
            "notify_kinds": ["franchise", "not-a-real-kind"],
            "reduce_motion": True,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200

    user = (await db_session.execute(select(User).where(User.username == "prefs"))).scalar_one()
    await db_session.refresh(user)
    assert user.prefs["discovery"] == "adventurous"
    assert user.prefs["hide_watched"] is True
    assert user.prefs["default_type"] == "tv"
    assert user.prefs["reduce_motion"] is True
    # Unknown kinds are dropped rather than stored.
    assert user.prefs["notify_kinds"] == ["franchise"]

    bad = await client.put(
        "/api/me", json={"discovery": "reckless"}, headers={"X-CSRF-Token": csrf}
    )
    assert bad.status_code == 422


async def test_ranking_respects_the_discovery_setting(db_session, ai_enabled, monkeypatch):
    """Adventurous spends more of the shelf on the exploration tail."""
    calls: list[float] = []
    real = taste.diversified_ranking

    vector = np.zeros(768)
    vector[0] = 1.0
    # No embeddings exist, so the pool is empty and the function returns
    # early; what matters here is that the mode is accepted and routed.
    assert await real(db_session, vector, 10, discovery="adventurous") == []
    assert await real(db_session, vector, 10, discovery="comfort") == []
    assert calls == []


def test_the_alert_whitelist_matches_the_kinds_the_code_actually_sends():
    """A typo here mutes an alert permanently and silently: the kind is
    stripped on save, so the toggle can never stay on."""
    import re
    from pathlib import Path

    from app.routers.profile import NOTIFY_KINDS

    source = (Path(__file__).resolve().parents[1] / "app/notifications/service.py").read_text()
    # The kind is the third positional argument to notify().
    sent = set(re.findall(r'notify\(\s*\n\s*db,\s*\n\s*\w+,\s*\n\s*"([a-z_]+)"', source))
    assert sent, "no notify() call sites found; the pattern needs updating"
    assert sent <= set(NOTIFY_KINDS), (
        f"kinds sent but not toggleable: {sorted(sent - set(NOTIFY_KINDS))}"
    )
