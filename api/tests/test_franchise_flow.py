"""Finishing one part of a franchise should answer what comes next."""

from sqlalchemy import select

from app.models import Title, User
from tests.util import LORDO, do_login

COLLECTION = {
    "id": 900,
    "name": "Example Collection",
    "overview": "Three films.",
    "poster_path": "/c.jpg",
    "backdrop_path": None,
    "parts": [
        {"id": 354912, "title": "Coco", "poster_path": "/p1.jpg", "release_date": "2017-10-27"},
        {
            "id": 550,
            "title": "Another Film",
            "poster_path": "/p2.jpg",
            "release_date": "2019-01-01",
        },
        {"id": 777, "title": "Third One", "poster_path": "/p3.jpg", "release_date": "2024-01-01"},
    ],
}


async def _csrf(client) -> dict:
    return {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}


async def _collection_fixture(monkeypatch):
    from app.catalog import tmdb

    async def fake_collection(db, collection_id):
        if collection_id != 900:
            raise tmdb.TmdbError("unknown collection")
        return COLLECTION

    monkeypatch.setattr(tmdb, "collection", fake_collection)


async def _streamable(db, client, user, tmdb_ids) -> None:
    """Next up only offers what can be watched at home, so a fixture with no
    availability rows correctly offers nothing. These tests are about which
    part comes next, not about where it plays, so pull the named parts into
    the catalog and put each on a service in the viewer's country."""
    from app.models import Availability, Title

    country = "US"
    user.country_code = country
    await db.commit()

    for tmdb_id in tmdb_ids:
        # Going through the API is what puts a title in the catalog.
        await client.get(f"/api/titles/movie/{tmdb_id}")
        title = (
            await db.execute(select(Title).where(Title.tmdb_id == tmdb_id))
        ).scalar_one_or_none()
        if title is None:
            continue
        exists = (
            (
                await db.execute(
                    select(Availability).where(
                        Availability.title_id == title.id, Availability.country == country
                    )
                )
            )
            .scalars()
            .first()
        )
        if exists is None:
            db.add(
                Availability(
                    title_id=title.id,
                    country=country,
                    provider_id=8,
                    provider_name="Netflix",
                    kind="stream",
                )
            )
    await db.commit()


async def test_next_up_points_at_the_first_unseen_part(
    client, fake_idp, fake_tmdb_http, db_session, monkeypatch
):
    await _collection_fixture(monkeypatch)
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf(client)

    await client.get("/api/titles/movie/354912")
    coco = (await db_session.execute(select(Title).where(Title.tmdb_id == 354912))).scalar_one()
    coco.collection_id = 900
    coco.collection_name = "Example Collection"
    await db_session.commit()

    user = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
    await _streamable(db_session, client, user, [354912, 550])

    # Nothing watched yet, so nothing to continue.
    assert (await client.get("/api/next-up")).json() == []

    await client.post("/api/history", json={"type": "movie", "tmdb_id": 354912}, headers=headers)
    body = (await client.get("/api/next-up")).json()
    assert len(body) == 1
    entry = body[0]
    assert entry["title"]["name"] == "Another Film", "the next one by release date"
    assert entry["reason"] == "You watched Coco"
    assert entry["collection_name"] == "Example Collection"
    # Counts parts they could actually start tonight. The third is not on
    # any service here, so it is not offered and not counted.
    assert entry["remaining"] == 1


async def test_a_like_is_enough_to_continue_a_franchise(
    client, fake_idp, fake_tmdb_http, db_session, monkeypatch
):
    await _collection_fixture(monkeypatch)
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf(client)
    await client.get("/api/titles/movie/354912")
    coco = (await db_session.execute(select(Title).where(Title.tmdb_id == 354912))).scalar_one()
    coco.collection_id = 900
    await db_session.commit()

    await client.post("/api/titles/movie/354912/signal", json={"kind": "like"}, headers=headers)
    user = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
    await _streamable(db_session, client, user, [354912, 550])
    body = (await client.get("/api/next-up")).json()
    assert body and body[0]["reason"] == "You liked Coco"


async def test_disliked_parts_are_not_offered(
    client, fake_idp, fake_tmdb_http, db_session, monkeypatch
):
    await _collection_fixture(monkeypatch)
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf(client)
    await client.get("/api/titles/movie/354912")
    await client.get("/api/titles/movie/550")
    for tmdb_id in (354912, 550):
        row = (await db_session.execute(select(Title).where(Title.tmdb_id == tmdb_id))).scalar_one()
        row.collection_id = 900
    await db_session.commit()

    await client.post("/api/history", json={"type": "movie", "tmdb_id": 354912}, headers=headers)
    await client.post("/api/titles/movie/550/signal", json={"kind": "dislike"}, headers=headers)
    user = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
    # The third part has to be streamable too, or skipping the disliked one
    # would leave nothing to offer and the test would pass for the wrong
    # reason.
    await _streamable(db_session, client, user, [354912, 550, 777])
    third = (await db_session.execute(select(Title).where(Title.tmdb_id == 777))).scalar_one()
    third.collection_id = 900
    await db_session.commit()

    body = (await client.get("/api/next-up")).json()
    assert body, "there is still a part left"
    assert body[0]["title"]["name"] != "Another Film", "a rejected part is skipped"


async def test_a_finished_franchise_disappears(
    client, fake_idp, fake_tmdb_http, db_session, monkeypatch
):
    from app.catalog import tmdb

    async def one_part(db, collection_id):
        return {"id": 900, "name": "Short Series", "parts": COLLECTION["parts"][:1]}

    monkeypatch.setattr(tmdb, "collection", one_part)
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf(client)
    await client.get("/api/titles/movie/354912")
    coco = (await db_session.execute(select(Title).where(Title.tmdb_id == 354912))).scalar_one()
    coco.collection_id = 900
    await db_session.commit()
    await client.post("/api/history", json={"type": "movie", "tmdb_id": 354912}, headers=headers)

    assert (await client.get("/api/next-up")).json() == [], "nothing left to continue"


async def test_franchise_notifications_fire_once(
    client, fake_idp, fake_tmdb_http, db_session, monkeypatch
):
    """A new entry in a franchise you enjoyed is announced, and only once."""
    from app.models import Notification
    from app.notifications import ntfy, service

    await _collection_fixture(monkeypatch)

    async def no_push(user, title, message):
        return False

    monkeypatch.setattr(ntfy, "push", no_push)

    await do_login(client, fake_idp, LORDO)
    headers = await _csrf(client)
    await client.get("/api/titles/movie/354912")
    coco = (await db_session.execute(select(Title).where(Title.tmdb_id == 354912))).scalar_one()
    coco.collection_id = 900
    await db_session.commit()
    await client.post("/api/history", json={"type": "movie", "tmdb_id": 354912}, headers=headers)

    first = await service.notify_new_franchise_parts(db_session)
    assert first["notifications"] == 2, "the two parts not in the catalog yet"

    rows = (
        (await db_session.execute(select(Notification).where(Notification.kind == "franchise")))
        .scalars()
        .all()
    )
    assert any("Example Collection" in r.message for r in rows)
    assert all("after you enjoyed Coco" in r.message for r in rows)

    second = await service.notify_new_franchise_parts(db_session)
    assert second["notifications"] == 0, "never announced twice"


async def test_no_franchise_interest_means_no_noise(
    client, fake_idp, fake_tmdb_http, db_session, monkeypatch
):
    from app.notifications import service

    await _collection_fixture(monkeypatch)
    await do_login(client, fake_idp, LORDO)
    result = await service.notify_new_franchise_parts(db_session)
    assert result == {"users": 0, "notifications": 0}
