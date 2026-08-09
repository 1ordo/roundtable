"""Marking a whole franchise watched, without double counting.

Saying "I have seen all of these" must not add a viewing to the one part you
already logged. The endpoint tops each part up to a target rather than
incrementing, and pressing it again with a higher target is how you say you
have been round the whole thing twice."""

from datetime import UTC, datetime

from sqlalchemy import func, select

from app.models import Title, User, WatchEvent
from tests.util import do_login

# Two parts of one collection, matching what the TMDB fake returns.
COLLECTION = {
    "id": 900,
    "name": "Test Collection",
    "overview": "",
    "poster_path": None,
    "backdrop_path": None,
    "parts": [
        {"id": 354912, "title": "Coco", "release_date": "2017-10-27", "poster_path": "/a.jpg"},
        {"id": 550, "title": "Fight Club", "release_date": "1999-10-15", "poster_path": "/b.jpg"},
    ],
}


async def setup(client, fake_idp, monkeypatch, username: str):
    from app.catalog import tmdb

    async def fake_collection(db, collection_id):
        return COLLECTION

    monkeypatch.setattr(tmdb, "collection", fake_collection)
    await do_login(client, fake_idp, {"sub": username, "preferred_username": username})
    return {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}


async def watch_count(db, username: str, tmdb_id: int) -> int:
    user = (await db.execute(select(User).where(User.username == username))).scalar_one()
    title = (await db.execute(select(Title).where(Title.tmdb_id == tmdb_id))).scalar_one()
    return (
        await db.execute(
            select(func.count(WatchEvent.id)).where(
                WatchEvent.user_id == user.id, WatchEvent.title_id == title.id
            )
        )
    ).scalar_one()


async def test_a_part_already_watched_is_not_counted_twice(
    client, fake_idp, db_session, monkeypatch, fake_tmdb_http, tmdb_key
):
    headers = await setup(client, fake_idp, monkeypatch, "franchise_fan")

    # Log one part by hand first, the way someone actually would.
    logged = await client.post(
        "/api/history", json={"type": "movie", "tmdb_id": 354912}, headers=headers
    )
    assert logged.status_code == 201

    result = await client.post("/api/collections/900/watched", json={"times": 1}, headers=headers)
    assert result.status_code == 200
    body = result.json()
    # Only the part that was behind gets a viewing.
    assert body["logged"] == 1
    assert body["already_counted"] == 1

    assert await watch_count(db_session, "franchise_fan", 354912) == 1, "not double counted"
    assert await watch_count(db_session, "franchise_fan", 550) == 1


async def test_pressing_it_again_at_the_same_target_changes_nothing(
    client, fake_idp, db_session, monkeypatch, fake_tmdb_http, tmdb_key
):
    headers = await setup(client, fake_idp, monkeypatch, "twice_clicker")

    first = await client.post("/api/collections/900/watched", json={"times": 1}, headers=headers)
    assert first.json()["logged"] == 2

    again = await client.post("/api/collections/900/watched", json={"times": 1}, headers=headers)
    assert again.json()["logged"] == 0, "the same target is idempotent"
    assert again.json()["already_counted"] == 2
    assert await watch_count(db_session, "twice_clicker", 354912) == 1


async def test_raising_the_target_adds_one_more_round(
    client, fake_idp, db_session, monkeypatch, fake_tmdb_http, tmdb_key
):
    headers = await setup(client, fake_idp, monkeypatch, "rewatcher")

    await client.post("/api/collections/900/watched", json={"times": 1}, headers=headers)
    second = await client.post("/api/collections/900/watched", json={"times": 2}, headers=headers)
    assert second.json()["logged"] == 2

    assert await watch_count(db_session, "rewatcher", 354912) == 2
    assert await watch_count(db_session, "rewatcher", 550) == 2


async def test_an_uneven_history_is_levelled_up_not_stacked(
    client, fake_idp, db_session, monkeypatch, fake_tmdb_http, tmdb_key
):
    """Someone who has seen one part three times and the other never should
    end up at three and three, not six and three."""
    from app.models import Title as T

    headers = await setup(client, fake_idp, monkeypatch, "uneven")
    for _ in range(3):
        await client.post(
            "/api/history", json={"type": "movie", "tmdb_id": 354912}, headers=headers
        )

    result = await client.post("/api/collections/900/watched", json={"times": 3}, headers=headers)
    assert result.json()["logged"] == 3  # only the part that was at zero
    assert await watch_count(db_session, "uneven", 354912) == 3
    assert await watch_count(db_session, "uneven", 550) == 3
    assert T is not None


async def test_the_collection_reports_how_many_full_rounds(
    client, fake_idp, monkeypatch, fake_tmdb_http, tmdb_key
):
    """One unwatched part means zero complete rounds, however many times the
    others have been seen."""
    headers = await setup(client, fake_idp, monkeypatch, "counter")

    await client.post("/api/history", json={"type": "movie", "tmdb_id": 354912}, headers=headers)
    partial = await client.get("/api/collections/900")
    assert partial.json()["times_all_watched"] == 0
    assert partial.json()["watched_count"] == 1

    await client.post("/api/collections/900/watched", json={"times": 1}, headers=headers)
    whole = await client.get("/api/collections/900")
    assert whole.json()["times_all_watched"] == 1


async def test_the_taste_vector_is_invalidated_when_anything_is_logged(
    client, fake_idp, db_session, monkeypatch, fake_tmdb_http, tmdb_key
):
    from app.models import UserTaste

    headers = await setup(client, fake_idp, monkeypatch, "taste_check")
    user = (
        await db_session.execute(select(User).where(User.username == "taste_check"))
    ).scalar_one()
    db_session.add(
        UserTaste(
            user_id=user.id,
            model="test",
            embedding=[0.0] * 768,
            events_count=5,
            computed_at=datetime.now(UTC),
        )
    )
    await db_session.commit()

    await client.post("/api/collections/900/watched", json={"times": 1}, headers=headers)
    row = (
        await db_session.execute(select(UserTaste).where(UserTaste.user_id == user.id))
    ).scalar_one()
    await db_session.refresh(row)
    assert row.events_count == -1, "a stale taste vector must be rebuilt after this"


class TestWatchableAtHome:
    """Next up must not suggest something you cannot watch tonight. A film
    still only playing in cinemas is the case that prompted this."""

    def test_an_unreleased_part_is_never_suggested(self):
        from app.routers.discovery import _watchable_at_home

        part = {"id": 1, "release_date": "2099-01-01"}
        assert _watchable_at_home(part, {}, set()) is False

    def test_a_part_with_no_release_date_is_not_suggested(self):
        from app.routers.discovery import _watchable_at_home

        assert _watchable_at_home({"id": 1, "release_date": None}, {}, set()) is False
        assert _watchable_at_home({"id": 1}, {}, set()) is False

    def test_released_but_cinema_only_is_not_suggested(self):
        """Out in cinemas, on nothing at home. The absence of any listing is
        the signal, since nothing marks a film as cinema-only."""
        from app.routers.discovery import _watchable_at_home

        class FakeTitle:
            id = "title-uuid"

        part = {"id": 7, "release_date": "2026-07-01"}
        known = {7: FakeTitle()}
        assert _watchable_at_home(part, known, set()) is False

    def test_released_and_streaming_is_suggested(self):
        from app.routers.discovery import _watchable_at_home

        class FakeTitle:
            id = "title-uuid"

        part = {"id": 7, "release_date": "2020-07-01"}
        known = {7: FakeTitle()}
        assert _watchable_at_home(part, known, {"title-uuid"}) is True

    def test_a_part_not_in_the_catalog_stays_quiet(self):
        """Nothing is known about where it plays, so saying nothing beats
        recommending something that turns out to be unwatchable."""
        from app.routers.discovery import _watchable_at_home

        assert _watchable_at_home({"id": 99, "release_date": "2020-01-01"}, {}, set()) is False
