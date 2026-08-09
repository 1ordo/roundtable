import copy

import pytest
from sqlalchemy import select

from app.models import Notification, User
from app.notifications import ntfy
from app.notifications.service import poll_availability
from tests import fixtures
from tests.util import FRIEND, LORDO, do_login


@pytest.fixture
def pushes(monkeypatch):
    sent: list[tuple[str, str, str]] = []

    async def fake_push(user, title, message):
        sent.append((user.username, title, message))
        return True

    monkeypatch.setattr(ntfy, "push", fake_push)
    return sent


@pytest.fixture
def mutable_movie(monkeypatch):
    """A copy of the Coco fixture the test can mutate between polls."""
    payload = copy.deepcopy(fixtures.MOVIE_DETAILS)
    monkeypatch.setattr(fixtures, "MOVIE_DETAILS", payload)
    return payload


async def _csrf_headers(client) -> dict:
    return {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}


async def _setup_watcher(client, fake_idp, db_session, country="EG", services=None):
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    await client.put(
        "/api/me",
        json={"country_code": country, "services": services or []},
        headers=headers,
    )
    lists = (await client.get("/api/lists", headers=headers)).json()["lists"]
    watchlist_id = next(lst["id"] for lst in lists if lst["kind"] == "watchlist")
    await client.post(
        f"/api/lists/{watchlist_id}/items",
        json={"type": "movie", "tmdb_id": 354912},
        headers=headers,
    )
    return headers


async def test_poller_notifies_on_new_provider(
    client, fake_idp, fake_tmdb_http, db_session, pushes, mutable_movie
):
    headers = await _setup_watcher(client, fake_idp, db_session)

    # First poll: rows already known from the ingest at add time, nothing new.
    counters = await poll_availability(db_session)
    assert counters["notifications"] == 0

    # Netflix appears in Egypt overnight.
    mutable_movie["watch/providers"]["results"]["EG"]["flatrate"].append(
        {"provider_id": 8, "provider_name": "Netflix", "logo_path": "/nf.jpg"}
    )

    counters = await poll_availability(db_session)
    assert counters["notifications"] == 1

    rows = (await db_session.execute(select(Notification))).scalars().all()
    assert len(rows) == 1
    assert "Netflix" in rows[0].message
    assert rows[0].sent_via == ["inbox", "ntfy"]
    assert pushes and pushes[0][0] == "Lordo"

    inbox = (await client.get("/api/notifications", headers=headers)).json()
    assert inbox["unread"] == 1
    assert inbox["notifications"][0]["title_tmdb_id"] == 354912


async def test_poller_respects_country_and_services(
    client, fake_idp, fake_tmdb_http, db_session, pushes, mutable_movie
):
    # Lordo is in Morocco and only subscribes to Disney Plus (337).
    await _setup_watcher(client, fake_idp, db_session, country="MA", services=[337])

    # New providers: Netflix in EG (wrong country) and Apple TV Plus in MA
    # (right country, not his service).
    mutable_movie["watch/providers"]["results"]["EG"]["flatrate"].append(
        {"provider_id": 8, "provider_name": "Netflix", "logo_path": "/nf.jpg"}
    )
    mutable_movie["watch/providers"]["results"]["MA"]["flatrate"] = [
        {"provider_id": 337, "provider_name": "Disney Plus", "logo_path": "/dp.jpg"},
        {"provider_id": 350, "provider_name": "Apple TV Plus", "logo_path": "/atv.jpg"},
    ]

    counters = await poll_availability(db_session)
    assert counters["new_rows"] >= 2
    assert counters["notifications"] == 0

    # Now Disney Plus adds a rent option in MA; that IS his service.
    mutable_movie["watch/providers"]["results"]["MA"].setdefault("rent", []).append(
        {"provider_id": 337, "provider_name": "Disney Plus", "logo_path": "/dp.jpg"}
    )
    counters = await poll_availability(db_session)
    assert counters["notifications"] == 1


async def test_no_country_means_no_alerts(
    client, fake_idp, fake_tmdb_http, db_session, pushes, mutable_movie
):
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    lists = (await client.get("/api/lists", headers=headers)).json()["lists"]
    watchlist_id = next(lst["id"] for lst in lists if lst["kind"] == "watchlist")
    await client.post(
        f"/api/lists/{watchlist_id}/items",
        json={"type": "movie", "tmdb_id": 354912},
        headers=headers,
    )
    mutable_movie["watch/providers"]["results"]["EG"]["flatrate"].append(
        {"provider_id": 8, "provider_name": "Netflix", "logo_path": "/nf.jpg"}
    )
    counters = await poll_availability(db_session)
    assert counters["notifications"] == 0


async def test_shared_list_notifies_both(
    client, fake_idp, fake_tmdb_http, db_session, pushes, mutable_movie
):
    # Nadia logs in first and sets her country.
    await do_login(client, fake_idp, FRIEND)
    headers_k = await _csrf_headers(client)
    await client.put("/api/me", json={"country_code": "EG"}, headers=headers_k)
    await client.post("/api/auth/logout", headers=headers_k)

    # Lordo adds the film to the shared list.
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    await client.put("/api/me", json={"country_code": "EG"}, headers=headers)
    lists = (await client.get("/api/lists", headers=headers)).json()["lists"]
    shared_id = next(lst["id"] for lst in lists if lst["kind"] == "shared")
    await client.post(
        f"/api/lists/{shared_id}/items",
        json={"type": "movie", "tmdb_id": 354912},
        headers=headers,
    )

    mutable_movie["watch/providers"]["results"]["EG"]["flatrate"].append(
        {"provider_id": 8, "provider_name": "Netflix", "logo_path": "/nf.jpg"}
    )
    counters = await poll_availability(db_session)
    assert counters["notifications"] == 2
    users = {
        (await db_session.execute(select(User).where(User.id == n.user_id))).scalar_one().username
        for n in (await db_session.execute(select(Notification))).scalars()
    }
    assert users == {"Lordo", "Nadia"}


async def test_inbox_read_flow(client, fake_idp, fake_tmdb_http, db_session, pushes, mutable_movie):
    headers = await _setup_watcher(client, fake_idp, db_session)
    mutable_movie["watch/providers"]["results"]["EG"]["flatrate"].append(
        {"provider_id": 8, "provider_name": "Netflix", "logo_path": "/nf.jpg"}
    )
    await poll_availability(db_session)

    inbox = (await client.get("/api/notifications", headers=headers)).json()
    assert inbox["unread"] == 1
    nid = inbox["notifications"][0]["id"]

    assert (await client.post(f"/api/notifications/{nid}/read", headers=headers)).status_code == 204
    assert (await client.get("/api/notifications", headers=headers)).json()["unread"] == 0

    # read-all is idempotent and safe on an already-read inbox.
    assert (await client.post("/api/notifications/read-all", headers=headers)).status_code == 204


async def test_inbox_is_private(
    client, fake_idp, fake_tmdb_http, db_session, pushes, mutable_movie
):
    headers = await _setup_watcher(client, fake_idp, db_session)
    mutable_movie["watch/providers"]["results"]["EG"]["flatrate"].append(
        {"provider_id": 8, "provider_name": "Netflix", "logo_path": "/nf.jpg"}
    )
    await poll_availability(db_session)
    await client.post("/api/auth/logout", headers=headers)

    await do_login(client, fake_idp, FRIEND)
    headers2 = await _csrf_headers(client)
    inbox = (await client.get("/api/notifications", headers=headers2)).json()
    assert inbox["unread"] == 0
    assert inbox["notifications"] == []
