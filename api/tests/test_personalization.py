"""The catalog grows as people browse, and home follows what they just did."""

from sqlalchemy import func, select

from app.models import Title, TitleEmbedding
from tests.util import LORDO, do_login


async def _csrf(client) -> dict:
    return {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}


async def test_opening_a_title_indexes_it_for_recommendations(
    client, fake_idp, fake_tmdb_http, db_session, ai_enabled
):
    """A title nobody had opened before becomes recommendable immediately."""
    before = (await db_session.execute(select(func.count(Title.id)))).scalar_one()
    assert before == 0

    await do_login(client, fake_idp, LORDO)
    resp = await client.get("/api/titles/movie/354912")
    assert resp.status_code == 200

    titles = (await db_session.execute(select(Title))).scalars().all()
    assert len(titles) == 1, "the click grew the catalog"

    vectors = (await db_session.execute(select(TitleEmbedding))).scalars().all()
    assert len(vectors) == 1, "and it is already indexed, no batch job needed"
    assert vectors[0].title_id == titles[0].id


async def test_saving_to_a_list_also_indexes(
    client, fake_idp, fake_tmdb_http, db_session, ai_enabled
):
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf(client)
    lists = (await client.get("/api/lists")).json()["lists"]
    watchlist = next(lst["id"] for lst in lists if lst["kind"] == "watchlist")

    await client.post(
        f"/api/lists/{watchlist}/items",
        json={"type": "movie", "tmdb_id": 550},
        headers=headers,
    )
    vectors = (await db_session.execute(select(TitleEmbedding))).scalars().all()
    assert len(vectors) == 1, "saving something indexes it too"


async def test_indexing_is_not_repeated(client, fake_idp, fake_tmdb_http, db_session, ai_enabled):
    await do_login(client, fake_idp, LORDO)
    await client.get("/api/titles/movie/354912")
    await client.get("/api/titles/movie/354912")
    count = (await db_session.execute(select(func.count(TitleEmbedding.title_id)))).scalar_one()
    assert count == 1, "one vector per title per model"


async def _widen_catalog(db, count: int = 10) -> None:
    """A row needs a handful of candidates before it is worth showing, so
    give the test a catalog the size of a real one."""
    from app.ai import embeddings

    for i in range(count):
        db.add(
            Title(
                tmdb_id=800000 + i,
                type="movie",
                name=f"Filler {i}",
                overview="A quiet drama about people in a small town.",
                genres=[{"id": 18, "name": "Drama"}],
                poster_path=f"/f{i}.jpg",
                popularity=5.0 + i,
            )
        )
    await db.flush()
    await embeddings.embed_missing_titles(db, limit=100)
    await db.commit()


async def test_home_follows_the_latest_click(
    client, fake_idp, fake_tmdb_http, db_session, ai_enabled
):
    """A row named after what you just engaged with, without the rest of the
    page rearranging."""
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf(client)
    for path in ("/api/titles/movie/354912", "/api/titles/tv/456", "/api/titles/movie/550"):
        await client.get(path)
    await _widen_catalog(db_session)

    def anchored(body: dict) -> list[dict]:
        return [r for r in body["rows"] if r["key"].startswith("because-")]

    # Nothing engaged with yet: no anchored row.
    assert anchored((await client.get("/api/home")).json()) == []

    await client.post("/api/titles/movie/354912/signal", json={"kind": "like"}, headers=headers)
    rows = anchored((await client.get("/api/home")).json())
    assert rows, "the newest signal earns a row"
    assert rows[0]["title"] == "Because you liked Coco"
    assert all(item["name"] != "Coco" for item in rows[0]["items"]), (
        "never recommends the thing it is named after"
    )

    # Engaging with something else puts the new anchor in front. Older ones
    # may stay, but only a couple: these are the rows that answer what you
    # did today, and a page of them is a page about your history instead.
    await client.post("/api/titles/tv/456/signal", json={"kind": "like"}, headers=headers)
    rows = anchored((await client.get("/api/home")).json())
    assert rows[0]["title"] == "Because you liked Example Show", "newest anchor leads"
    assert len(rows) <= 2, "a couple of them, not a growing pile"
    assert len({r["key"] for r in rows}) == len(rows), "distinct keys, so React can tell them apart"


async def test_stable_rows_keep_their_order(
    client, fake_idp, fake_tmdb_http, db_session, ai_enabled
):
    """Personalization must not reshuffle the shelf under the viewer."""
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf(client)
    await client.get("/api/titles/movie/354912")
    await _widen_catalog(db_session)

    first = [r["key"] for r in (await client.get("/api/home")).json()["rows"]]
    await client.post("/api/titles/movie/354912/signal", json={"kind": "like"}, headers=headers)
    second = [r["key"] for r in (await client.get("/api/home")).json()["rows"]]

    # Everything that was there before is still there, in the same order.
    kept = [key for key in second if key in first]
    assert kept == first, "existing rows stay put; personal rows are added on top"
