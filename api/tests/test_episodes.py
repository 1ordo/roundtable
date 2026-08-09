"""Episode tracking: progress, next up, and the new-episode alert.

A show is a position, not a checkbox, so the tests that matter are the ones
about where that position is: an unaired episode must never count, a special
must never block the queue, and a binge must record every episode rather
than one.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.catalog import episodes as service
from app.models import Episode, List, ListItem, Notification, Title, User, WatchEvent
from tests.util import do_login


async def a_show(db, tmdb_id: int = 999701, name: str = "A Series") -> Title:
    show = Title(tmdb_id=tmdb_id, type="tv", name=name)
    db.add(show)
    await db.flush()
    return show


async def add_episode(
    db, show: Title, season: int, number: int, air: date | None, name: str | None = None
) -> Episode:
    episode = Episode(
        title_id=show.id,
        season_number=season,
        episode_number=number,
        name=name or f"Episode {number}",
        air_date=air,
    )
    db.add(episode)
    await db.flush()
    return episode


class TestProgress:
    async def test_an_unaired_episode_is_not_part_of_progress(self, client, fake_idp, db_session):
        """Otherwise every currently running show reads as half watched and
        nobody is ever up to date."""
        await do_login(client, fake_idp, {"sub": "e1", "preferred_username": "watcher_e1"})
        user = (
            await db_session.execute(select(User).where(User.username == "watcher_e1"))
        ).scalar_one()
        show = await a_show(db_session)
        today = datetime.now(UTC).date()
        first = await add_episode(db_session, show, 1, 1, today - timedelta(days=14))
        await add_episode(db_session, show, 1, 2, today - timedelta(days=7))
        await add_episode(db_session, show, 1, 3, today + timedelta(days=7))
        await db_session.commit()

        await service.mark_watched(db_session, user, show, first)
        await db_session.commit()

        stats = await service.progress(db_session, user, show)
        assert stats["aired"] == 2, "the future episode is not part of the total"
        assert stats["watched"] == 1
        assert stats["upcoming"] == 1
        assert stats["complete"] is False

    async def test_a_show_is_complete_when_everything_aired_is_watched(
        self, client, fake_idp, db_session
    ):
        await do_login(client, fake_idp, {"sub": "e2", "preferred_username": "watcher_e2"})
        user = (
            await db_session.execute(select(User).where(User.username == "watcher_e2"))
        ).scalar_one()
        show = await a_show(db_session, 999702)
        today = datetime.now(UTC).date()
        one = await add_episode(db_session, show, 1, 1, today - timedelta(days=3))
        two = await add_episode(db_session, show, 1, 2, today - timedelta(days=1))
        await add_episode(db_session, show, 1, 3, today + timedelta(days=6))
        await db_session.commit()

        await service.mark_watched(db_session, user, show, one)
        await service.mark_watched(db_session, user, show, two)
        await db_session.commit()

        stats = await service.progress(db_session, user, show)
        assert stats["complete"] is True, "caught up counts as complete even mid-run"
        assert await service.next_up(db_session, user, show) is None

    async def test_an_episode_with_no_air_date_never_counts(self, client, fake_idp, db_session):
        """TMDB lists announced episodes with no date. They are not out."""
        await do_login(client, fake_idp, {"sub": "e3", "preferred_username": "watcher_e3"})
        user = (
            await db_session.execute(select(User).where(User.username == "watcher_e3"))
        ).scalar_one()
        show = await a_show(db_session, 999703)
        await add_episode(db_session, show, 1, 1, None)
        await db_session.commit()

        stats = await service.progress(db_session, user, show)
        assert stats["aired"] == 0
        assert await service.next_up(db_session, user, show) is None


class TestNextUp:
    async def test_next_up_is_the_earliest_unwatched_aired_episode(
        self, client, fake_idp, db_session
    ):
        await do_login(client, fake_idp, {"sub": "e4", "preferred_username": "watcher_e4"})
        user = (
            await db_session.execute(select(User).where(User.username == "watcher_e4"))
        ).scalar_one()
        show = await a_show(db_session, 999704)
        today = datetime.now(UTC).date()
        one = await add_episode(db_session, show, 1, 1, today - timedelta(days=30))
        await add_episode(db_session, show, 1, 2, today - timedelta(days=23))
        await add_episode(db_session, show, 2, 1, today - timedelta(days=16))
        await db_session.commit()

        await service.mark_watched(db_session, user, show, one)
        await db_session.commit()

        nxt = await service.next_up(db_session, user, show)
        assert nxt is not None
        assert (nxt.season_number, nxt.episode_number) == (1, 2)

    async def test_a_special_never_blocks_the_queue(self, client, fake_idp, db_session):
        """Season 0 is TMDB's specials bucket. Pointing next-up at one would
        stall a show forever on something nobody knew existed."""
        await do_login(client, fake_idp, {"sub": "e5", "preferred_username": "watcher_e5"})
        user = (
            await db_session.execute(select(User).where(User.username == "watcher_e5"))
        ).scalar_one()
        show = await a_show(db_session, 999705)
        today = datetime.now(UTC).date()
        await add_episode(db_session, show, 0, 1, today - timedelta(days=40), "A Christmas thing")
        one = await add_episode(db_session, show, 1, 1, today - timedelta(days=30))
        await add_episode(db_session, show, 1, 2, today - timedelta(days=23))
        await db_session.commit()

        await service.mark_watched(db_session, user, show, one)
        await db_session.commit()

        nxt = await service.next_up(db_session, user, show)
        assert nxt is not None
        assert nxt.season_number == 1, "a special is never next up"
        assert nxt.episode_number == 2


class TestMarking:
    async def test_marking_the_same_episode_twice_records_one_watch(
        self, client, fake_idp, db_session
    ):
        """The extension reports the same episode repeatedly as playback
        advances, so this has to be idempotent."""
        await do_login(client, fake_idp, {"sub": "e6", "preferred_username": "watcher_e6"})
        user = (
            await db_session.execute(select(User).where(User.username == "watcher_e6"))
        ).scalar_one()
        show = await a_show(db_session, 999706)
        one = await add_episode(
            db_session, show, 1, 1, datetime.now(UTC).date() - timedelta(days=2)
        )
        await db_session.commit()

        assert await service.mark_watched(db_session, user, show, one) is True
        assert await service.mark_watched(db_session, user, show, one) is False
        await db_session.commit()

        count = len(
            (
                await db_session.execute(
                    select(WatchEvent).where(
                        WatchEvent.user_id == user.id, WatchEvent.episode_id == one.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert count == 1

    async def test_four_episodes_in_one_evening_are_four_watches(
        self, client, fake_idp, db_session
    ):
        """The old sitting window collapsed a binge into a single watch of
        the whole series, which is the bug episodes exist to fix."""
        await do_login(client, fake_idp, {"sub": "e7", "preferred_username": "watcher_e7"})
        user = (
            await db_session.execute(select(User).where(User.username == "watcher_e7"))
        ).scalar_one()
        show = await a_show(db_session, 999707)
        today = datetime.now(UTC).date()
        made = [
            await add_episode(db_session, show, 1, n, today - timedelta(days=10))
            for n in range(1, 5)
        ]
        await db_session.commit()

        for episode in made:
            await service.mark_watched(db_session, user, show, episode)
        await db_session.commit()

        events = (
            (
                await db_session.execute(
                    select(WatchEvent).where(
                        WatchEvent.user_id == user.id, WatchEvent.title_id == show.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 4


class TestNewEpisodeAlerts:
    async def test_a_new_episode_of_a_show_you_watch_is_announced_once(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key, monkeypatch
    ):
        from app.notifications import service as notifications

        await do_login(client, fake_idp, {"sub": "e8", "preferred_username": "follower_e8"})
        user = (
            await db_session.execute(select(User).where(User.username == "follower_e8"))
        ).scalar_one()
        show = await a_show(db_session, 999708, "Ongoing Show")
        today = datetime.now(UTC).date()
        first = await add_episode(db_session, show, 1, 1, today - timedelta(days=7))
        await add_episode(db_session, show, 1, 2, today, "The new one")
        await db_session.commit()

        # They are watching it: one episode already logged.
        await service.mark_watched(db_session, user, show, first)
        await db_session.commit()

        # No TMDB round trip in the test; the episodes are already local.
        async def no_sync(db, title, payload=None):
            return 0

        monkeypatch.setattr(service, "sync_series", no_sync)

        result = await notifications.notify_new_episodes(db_session)
        assert result["notifications"] >= 1

        sent = (
            (
                await db_session.execute(
                    select(Notification).where(
                        Notification.user_id == user.id, Notification.kind == "episode"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(sent) == 1
        assert "S1E2" in sent[0].message
        assert sent[0].episode_id is not None

        again = await notifications.notify_new_episodes(db_session)
        assert again["notifications"] == 0, "once per person per episode"

    async def test_an_unaired_episode_is_not_announced(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key, monkeypatch
    ):
        from app.notifications import service as notifications

        await do_login(client, fake_idp, {"sub": "e9", "preferred_username": "follower_e9"})
        user = (
            await db_session.execute(select(User).where(User.username == "follower_e9"))
        ).scalar_one()
        show = await a_show(db_session, 999709, "Not Out Yet")
        today = datetime.now(UTC).date()
        first = await add_episode(db_session, show, 1, 1, today - timedelta(days=7))
        await add_episode(db_session, show, 1, 2, today + timedelta(days=7))
        await db_session.commit()
        await service.mark_watched(db_session, user, show, first)
        await db_session.commit()

        async def no_sync(db, title, payload=None):
            return 0

        monkeypatch.setattr(service, "sync_series", no_sync)

        await notifications.notify_new_episodes(db_session)
        sent = (
            (
                await db_session.execute(
                    select(Notification).where(
                        Notification.user_id == user.id, Notification.kind == "episode"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert sent == []

    async def test_a_show_only_on_a_list_still_counts_as_followed(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key, monkeypatch
    ):
        """Keeping a show on a list is a statement of interest made in
        advance, so it should behave like having watched one."""
        from app.notifications import service as notifications

        await do_login(client, fake_idp, {"sub": "e10", "preferred_username": "lister_e10"})
        user = (
            await db_session.execute(select(User).where(User.username == "lister_e10"))
        ).scalar_one()
        show = await a_show(db_session, 999710, "Saved For Later")
        await add_episode(db_session, show, 1, 1, datetime.now(UTC).date())

        listing = List(
            tenant_id=user.tenant_id, user_id=user.id, name="Watchlist", kind="watchlist"
        )
        db_session.add(listing)
        await db_session.flush()
        db_session.add(ListItem(list_id=listing.id, title_id=show.id))
        await db_session.commit()

        async def no_sync(db, title, payload=None):
            return 0

        monkeypatch.setattr(service, "sync_series", no_sync)

        result = await notifications.notify_new_episodes(db_session)
        assert result["notifications"] >= 1


class TestTheApi:
    async def test_switching_off_episode_alerts_is_respected(self, client, fake_idp, db_session):
        from app.notifications.service import wants

        await do_login(client, fake_idp, {"sub": "e11", "preferred_username": "quiet_e11"})
        user = (
            await db_session.execute(select(User).where(User.username == "quiet_e11"))
        ).scalar_one()
        assert wants(user, "episode") is True, "on by default"

        user.prefs = {"notify_kinds": ["availability"]}
        assert wants(user, "episode") is False

    @pytest.mark.parametrize("kind", ["message", "friend_request", "night_invite", "cinema"])
    async def test_a_legacy_preference_does_not_mute_everything(
        self, client, fake_idp, db_session, kind
    ):
        """The old settings screen could only ever save four keys, two of
        which were never real. Such a list must not be read as a decision to
        mute the kinds it could not name."""
        from app.notifications.service import wants

        await do_login(client, fake_idp, {"sub": f"e12{kind}", "preferred_username": f"old_{kind}"})
        user = (
            await db_session.execute(select(User).where(User.username == f"old_{kind}"))
        ).scalar_one()
        user.prefs = {"notify_kinds": ["availability", "franchise", "like", "shared"]}
        assert wants(user, kind) is True
