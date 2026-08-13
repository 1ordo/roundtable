"""Franchises, people, and the parents guide."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.catalog.ingest import extract_certifications
from app.models import List, ListItem, Title, User
from app.routers.discovery import _credit
from tests.util import LORDO, do_login


def test_movie_certifications_come_from_release_dates():
    payload = {
        "release_dates": {
            "results": [
                {
                    "iso_3166_1": "US",
                    "release_dates": [
                        {"certification": "", "type": 1},
                        {"certification": "PG-13", "type": 3},
                    ],
                },
                {"iso_3166_1": "GB", "release_dates": [{"certification": "12A", "type": 3}]},
                {"iso_3166_1": "EG", "release_dates": [{"certification": "", "type": 3}]},
            ]
        }
    }
    certs = extract_certifications("movie", payload)
    assert certs == {"US": "PG-13", "GB": "12A"}
    assert "EG" not in certs, "a blank rating is missing data, not a rating"


def test_series_certifications_come_from_content_ratings():
    payload = {
        "content_ratings": {
            "results": [
                {"iso_3166_1": "US", "rating": "TV-MA"},
                {"iso_3166_1": "DE", "rating": "16"},
                {"iso_3166_1": "FR", "rating": ""},
            ]
        }
    }
    assert extract_certifications("tv", payload) == {"US": "TV-MA", "DE": "16"}


def test_no_ratings_means_an_empty_map():
    assert extract_certifications("movie", {}) == {}
    assert extract_certifications("tv", {"content_ratings": {"results": []}}) == {}


def test_certification_prefers_the_viewers_country():
    from app.routers.catalog import _certification_for

    class FakeTitle:
        certifications = {"US": "R", "GB": "18", "EG": "18+"}

    class FakeUser:
        country_code = "EG"

    assert _certification_for(FakeTitle(), FakeUser()) == "18+"

    class Elsewhere:
        country_code = "JP"

    assert _certification_for(FakeTitle(), Elsewhere()) == "R", "falls back to a known board"

    class NoCerts:
        certifications: dict = {}

    assert _certification_for(NoCerts(), FakeUser()) is None


def test_person_credits_drop_appearances_as_themselves():
    """Talk shows are not an actor's filmography."""
    assert (
        _credit({"media_type": "tv", "id": 1, "name": "The Tonight Show", "genre_ids": [10767]})
        is None
    )
    assert _credit({"media_type": "tv", "id": 2, "name": "The News", "genre_ids": [10763]}) is None
    assert _credit({"media_type": "movie", "id": 3, "title": "Doc", "character": "Self"}) is None

    real = _credit(
        {
            "media_type": "movie",
            "id": 4,
            "title": "Spider-Man",
            "character": "Peter Parker",
            "release_date": "2021-12-15",
            "genre_ids": [28],
        }
    )
    assert real is not None
    assert real.name == "Spider-Man"
    assert real.year == 2021
    assert real.character == "Peter Parker"


def test_credits_ignore_other_media_types():
    assert _credit({"media_type": "person", "id": 5}) is None


async def test_parents_guide_is_opt_in(client, fake_idp, db_session):
    await do_login(client, fake_idp, LORDO)
    headers = {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}

    me = (await client.get("/api/me")).json()
    assert me["user"]["prefs"].get("parents_guide") is None, "off until asked for"

    resp = await client.put("/api/me", json={"parents_guide": True}, headers=headers)
    assert resp.status_code == 200
    me = (await client.get("/api/me")).json()
    assert me["user"]["prefs"]["parents_guide"] is True

    await client.put("/api/me", json={"parents_guide": False}, headers=headers)
    me = (await client.get("/api/me")).json()
    assert me["user"]["prefs"]["parents_guide"] is False


async def test_bulk_add_saves_a_whole_franchise(client, fake_idp, fake_tmdb_http, db_session):
    await do_login(client, fake_idp, LORDO)
    headers = {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}

    resp = await client.post(
        "/api/lists/bulk",
        json={
            "titles": [
                {"type": "movie", "tmdb_id": 354912},
                {"type": "movie", "tmdb_id": 550},
                {"type": "tv", "tmdb_id": 456},
            ]
        },
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["added"] == 3
    assert body["already_there"] == 0
    assert body["list_name"]

    # Running it again is harmless, and says so.
    again = await client.post(
        "/api/lists/bulk",
        json={"titles": [{"type": "movie", "tmdb_id": 354912}]},
        headers=headers,
    )
    assert again.json() == {
        "added": 0,
        "already_there": 1,
        "failed": 0,
        "list_name": body["list_name"],
    }


async def test_bulk_add_reports_what_it_could_not_take(
    client, fake_idp, fake_tmdb_http, db_session
):
    await do_login(client, fake_idp, LORDO)
    headers = {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}
    resp = await client.post(
        "/api/lists/bulk",
        json={"titles": [{"type": "book", "tmdb_id": 1}, {"type": "movie", "tmdb_id": "x"}]},
        headers=headers,
    )
    assert resp.json()["failed"] == 2
    assert resp.json()["added"] == 0


async def test_bulk_add_needs_csrf(client, fake_idp):
    await do_login(client, fake_idp, LORDO)
    resp = await client.post("/api/lists/bulk", json={"titles": [{"type": "movie", "tmdb_id": 1}]})
    assert resp.status_code == 403


class TestSavingAWholeFranchise:
    """The assistant proposed 72 Marvel titles and the save refused them.

    Two numbers, picked in two files, that had to agree and did not. The
    resolver returns up to five pages of twenty for films and again for
    series; the save capped a request at sixty. Every Marvel proposal the
    assistant made was unsaveable, and Marvel is the franchise people ask
    for by name.
    """

    def test_the_save_accepts_everything_the_resolver_can_propose(self):
        """The invariant, stated once. Whatever a watch order can contain,
        a save has to be able to carry, or the assistant offers a button
        that cannot work."""
        from app.catalog import watch_order
        from app.routers.discovery import BulkAddBody

        BulkAddBody(titles=[{"type": "movie", "tmdb_id": n} for n in range(watch_order.MAX_TITLES)])

    async def test_seventy_two_titles_save_without_refetching_any_of_them(
        self, client, fake_idp, fake_tmdb_http, db_session
    ):
        """The size the Marvel universe actually resolves to, and the second
        half of the same bug: every row was already in the catalog, but
        ensure_title refreshes anything older than a day, so the save made
        one TMDB call per title to write rows it already had."""
        await do_login(client, fake_idp, LORDO)
        me = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
        assert me is not None

        stale = datetime(2020, 1, 1, tzinfo=UTC)
        for n in range(72):
            db_session.add(
                Title(
                    tmdb_id=900_000 + n,
                    type="movie",
                    name=f"Marvel Thing {n}",
                    details_refreshed_at=stale,
                )
            )
        await db_session.commit()

        headers = {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}
        fake_tmdb_http.clear()
        resp = await client.post(
            "/api/lists/bulk",
            json={
                "name": "Marvel Cinematic Universe",
                "titles": [{"type": "movie", "tmdb_id": 900_000 + n} for n in range(72)],
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["added"] == 72
        assert body["failed"] == 0
        assert body["list_name"] == "Marvel Cinematic Universe"

        detail_calls = [p for p in fake_tmdb_http if p.startswith(("/movie/", "/tv/"))]
        assert detail_calls == [], f"a save should not refresh the catalog, made {detail_calls}"

    async def test_the_order_proposed_is_the_order_saved(
        self, client, fake_idp, fake_tmdb_http, db_session
    ):
        """A watch-through that renders in any other order is not one."""
        await do_login(client, fake_idp, LORDO)
        for n in range(3):
            db_session.add(Title(tmdb_id=910_000 + n, type="movie", name=f"Part {n}"))
        await db_session.commit()

        headers = {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}
        await client.post(
            "/api/lists/bulk",
            json={
                "name": "In Order",
                "titles": [{"type": "movie", "tmdb_id": 910_002 - n} for n in range(3)],
            },
            headers=headers,
        )
        rows = (
            (
                await db_session.execute(
                    select(Title.tmdb_id)
                    .join(ListItem, ListItem.title_id == Title.id)
                    .join(List, List.id == ListItem.list_id)
                    .where(List.name == "In Order")
                    .order_by(ListItem.position)
                )
            )
            .scalars()
            .all()
        )
        assert list(rows) == [910_002, 910_001, 910_000]
