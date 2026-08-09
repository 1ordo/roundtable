"""With no TMDB key the app must still work off the local catalog, which is
what OMDb fills. These build the catalog the way the OMDb importer does."""

from datetime import UTC, datetime

from app.models import Title
from tests.util import LORDO, do_login

OMDB_INCEPTION = {
    "Title": "Inception",
    "Year": "2010",
    "Rated": "PG-13",
    "Runtime": "148 min",
    "Genre": "Action, Adventure, Sci-Fi",
    "Director": "Christopher Nolan",
    "Actors": "Leonardo DiCaprio, Joseph Gordon-Levitt",
    "Plot": "A thief who steals corporate secrets through dream-sharing technology.",
    "Language": "English, Japanese",
    "Country": "United States",
    "Awards": "Won 4 Oscars.",
    "Poster": "https://m.media-amazon.com/images/M/inception._V1_SX300.jpg",
    "Ratings": [{"Source": "Rotten Tomatoes", "Value": "87%"}],
    "Metascore": "74",
    "imdbRating": "8.8",
    "imdbVotes": "2,500,000",
    "imdbID": "tt1375666",
    "Type": "movie",
    "Response": "True",
}

OMDB_PARASITE = {
    "Title": "Parasite",
    "Year": "2019",
    "Runtime": "132 min",
    "Genre": "Drama, Thriller",
    "Director": "Bong Joon Ho",
    "Actors": "Song Kang-ho",
    "Plot": "Greed and class discrimination threaten a newly formed relationship.",
    "Language": "Korean",
    "Country": "South Korea",
    "Poster": "https://m.media-amazon.com/images/M/parasite._V1_SX300.jpg",
    "imdbRating": "8.5",
    "imdbVotes": "900,000",
    "imdbID": "tt6751668",
    "Type": "movie",
    "Response": "True",
}

OMDB_BREAKING_BAD = {
    "Title": "Breaking Bad",
    "Year": "2008",
    "Runtime": "49 min",
    "Genre": "Crime, Drama, Thriller",
    "Director": "N/A",
    "Actors": "Bryan Cranston",
    "Plot": "A chemistry teacher turns to making methamphetamine.",
    "Language": "English",
    "Country": "United States",
    "Poster": "https://m.media-amazon.com/images/M/bb._V1_SX300.jpg",
    "imdbRating": "9.5",
    "imdbVotes": "2,100,000",
    "imdbID": "tt0903747",
    "Type": "series",
    "Response": "True",
}


async def _build_catalog(db) -> None:
    from app.catalog import omdb_source

    for payload in (OMDB_INCEPTION, OMDB_PARASITE, OMDB_BREAKING_BAD):
        await omdb_source.upsert_from_omdb(db, payload)
    await db.commit()


async def test_omdb_payload_becomes_a_real_title(client, fake_idp, db_session):
    from sqlalchemy import select

    await _build_catalog(db_session)
    title = (
        await db_session.execute(select(Title).where(Title.imdb_id == "tt1375666"))
    ).scalar_one()

    assert title.name == "Inception"
    assert title.year == 2010
    assert title.runtime == 148
    assert title.original_language == "en"
    assert {g["id"] for g in title.genres} == {28, 12, 878}
    assert title.poster_path and title.poster_path.startswith("https://")
    assert title.imdb_rating == 8.8
    assert title.rt_score == 87
    assert title.metacritic == 74
    assert title.tmdb_votes == 2_500_000
    assert title.raw_tmdb["director"] == "Christopher Nolan"
    assert title.type == "movie"

    series = (
        await db_session.execute(select(Title).where(Title.imdb_id == "tt0903747"))
    ).scalar_one()
    assert series.type == "tv", "OMDb series map to tv"


async def test_home_browse_and_search_work_without_tmdb(client, fake_idp, db_session):
    await _build_catalog(db_session)
    await do_login(client, fake_idp, LORDO)

    home = await client.get("/api/home")
    assert home.status_code == 200
    rows = home.json()["rows"]
    assert rows, "home falls back to the local catalog"
    names = {item["name"] for row in rows for item in row["items"]}
    assert "Inception" in names

    # Language grouping reads the real language field rather than guessing.
    from app.catalog import local

    korean = await local.by_language(db_session, "ko")
    assert [t.name for t in korean] == ["Parasite"]

    genres = await client.get("/api/genres")
    assert genres.status_code == 200
    assert genres.json()["movie"], "browse chips come from local genres"

    browse = await client.get("/api/browse", params={"type": "movie", "genre": 878})
    assert browse.status_code == 200
    assert any(r["name"] == "Inception" for r in browse.json()["results"])

    found = await client.get("/api/search", params={"q": "parasite"})
    assert found.status_code == 200
    assert any(r["name"] == "Parasite" for r in found.json()["results"])


async def test_title_detail_opens_without_tmdb(client, fake_idp, db_session):
    from sqlalchemy import select

    await _build_catalog(db_session)
    await do_login(client, fake_idp, LORDO)
    title = (
        await db_session.execute(select(Title).where(Title.imdb_id == "tt1375666"))
    ).scalar_one()

    resp = await client.get(f"/api/titles/movie/{title.tmdb_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Inception"
    assert body["director"] == "Christopher Nolan"
    assert body["awards"].startswith("Won 4 Oscars")
    assert body["imdb_id"] == "tt1375666"
    assert body["rated"] == "PG-13"


async def test_upsert_is_idempotent(client, db_session):
    from sqlalchemy import func, select

    await _build_catalog(db_session)
    first = (await db_session.execute(select(func.count(Title.id)))).scalar_one()
    await _build_catalog(db_session)
    second = (await db_session.execute(select(func.count(Title.id)))).scalar_one()
    assert first == second == 3


async def test_empty_database_still_reports_setup(client, fake_idp):
    await do_login(client, fake_idp, LORDO)
    resp = await client.get("/api/home")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "tmdb_not_configured"


async def test_match_scores_reflect_user_signals(client, fake_idp, db_session, ai_enabled):
    """Everything the person does feeds one number on every card."""
    from sqlalchemy import select

    from app.ai import embeddings, taste
    from app.models import Interaction, User

    await _build_catalog(db_session)
    await embeddings.embed_missing_titles(db_session)
    await db_session.commit()

    await do_login(client, fake_idp, LORDO)
    user = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()

    # No signals yet: no scores, and the UI simply omits the badge.
    ids = list((await db_session.execute(select(Title.id))).scalars())
    assert await taste.match_scores(db_session, user, ids) == {}

    parasite = (
        await db_session.execute(select(Title).where(Title.imdb_id == "tt6751668"))
    ).scalar_one()
    db_session.add(Interaction(user_id=user.id, title_id=parasite.id, kind="like"))
    await db_session.commit()

    scores = await taste.match_scores(db_session, user, ids)
    await db_session.commit()
    assert scores, "a single like is enough to start scoring"
    assert all(0 <= value <= 100 for value in scores.values())
    assert scores[parasite.id] == max(scores.values()), "the liked title fits best"


def test_local_encoder_is_a_usable_vector_space():
    from app.ai import local_embedding

    def cosine(a: list[float], b: list[float]) -> float:
        return sum(x * y for x, y in zip(a, b, strict=True))

    crime = local_embedding.encode("A Seoul crime thriller about class and greed, Korean")
    similar = local_embedding.encode("Korean thriller about greed and social class in Seoul")
    unrelated = local_embedding.encode("A gentle animated film about a young musician")

    assert len(crime) == local_embedding.DIM
    assert abs(cosine(crime, crime) - 1.0) < 1e-6, "normalised"
    assert cosine(crime, similar) > cosine(crime, unrelated) * 2, "meaningful separation"
    assert local_embedding.encode("stable") == local_embedding.encode("stable")
    # Non-latin scripts still produce meaningful neighbours.
    arabic_a = local_embedding.encode("فيلم دراما مصري عن القاهرة")
    arabic_b = local_embedding.encode("دراما مصرية في القاهرة")
    assert cosine(arabic_a, arabic_b) > cosine(arabic_a, unrelated)


async def test_seed_accounts_enables_password_login(client, db_session):
    from app.seed import seed_accounts

    await seed_accounts()
    resp = await client.post(
        "/api/auth/password/login",
        json={"username": "Lordo", "password": "watchpile-local"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


async def test_no_invented_titles_are_created(client, db_session):
    """The seed must never fabricate catalog entries."""
    from sqlalchemy import func, select

    from app.seed import seed_accounts

    await seed_accounts()
    count = (await db_session.execute(select(func.count(Title.id)))).scalar_one()
    assert count == 0, "accounts only; titles come from a real provider"


async def test_service_list_is_the_curated_set(client, fake_idp):
    await do_login(client, fake_idp, LORDO)
    resp = await client.get("/api/services")
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()]
    for expected in ["Netflix", "Prime Video", "Disney+", "HBO Max", "Shahid", "Watch It"]:
        assert expected in names


async def test_new_page_sections_follow_subscriptions(client, fake_idp, db_session):
    await _build_catalog(db_session)
    await do_login(client, fake_idp, LORDO)
    headers = {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}
    await client.put("/api/me", json={"services": [8], "country_code": "EG"}, headers=headers)

    mine = (await client.get("/api/new")).json()
    assert [s["service"]["name"] for s in mine["services"]] == ["Netflix"]
    assert mine["services"][0]["unknown"] is True, "no availability data yet, said honestly"

    every = (await client.get("/api/new", params={"all": "true"})).json()
    assert len(every["services"]) > 1
    assert every["showing_all_services"] is True


def test_bootstrap_titles_are_real_names():
    """The bootstrap list is names only: every field shown to a user comes
    back from the provider, never from this repository."""
    from app.catalog import bootstrap

    assert len(bootstrap.TITLES) > 100
    assert all(isinstance(name, str) and name.strip() for name in bootstrap.TITLES)
    assert len(set(bootstrap.TITLES)) >= len(bootstrap.TITLES) - 2
    assert "Parasite" in bootstrap.TITLES
    assert any(name == "Capernaum" for name in bootstrap.TITLES)


def test_datetime_import_is_used():
    assert datetime.now(UTC).tzinfo is UTC


def test_series_year_ranges_become_the_start_year():
    """OMDb reports a run like "2008-2013" for series."""
    from app.catalog.omdb_source import _year_or_none

    assert _year_or_none("2008-2013") == 2008
    assert _year_or_none("2008–2013") == 2008, "en dash too"
    assert _year_or_none("2019-") == 2019, "still running"
    assert _year_or_none("2010") == 2010
    assert _year_or_none("N/A") is None
    assert _year_or_none(None) is None


def test_service_ids_cover_tmdb_regional_variants():
    """TMDB lists one service under several provider ids: a different one
    per region, plus ad tiers and channel resellers. Availability matching
    must accept all of them."""
    from app.catalog import services

    prime = services.BY_ID[9]
    assert 119 in prime["ids"], "the id TMDB uses in Egypt and Morocco"
    assert 9 in prime["ids"]

    netflix = services.BY_ID[8]
    assert 1796 in netflix["ids"], "Netflix with ads"

    # Every alias resolves back to exactly one service.
    for provider_id, service in services.ALIASES.items():
        assert service in services.SERVICES
        assert provider_id in service["ids"]

    # The regional services TMDB actually reports for his countries.
    names = {s["name"] for s in services.SERVICES}
    assert {"Shahid", "OSN+", "STARZPLAY"} <= names

    assert services.provider_ids_for(9) == prime["ids"]
    assert services.provider_ids_for(99999) == [99999], "unknown ids pass through"


def test_click_out_uses_the_service_search():
    from app.catalog import services

    url = services.search_url(119, "Dune: Part Two")
    assert url is not None
    assert url.startswith("https://www.primevideo.com/"), "the alias maps to Prime Video"
    assert "Dune" in url


async def test_omdb_upsert_survives_duplicate_imdb_ids(db_session):
    """A TMDB-native row and the OMDb surrogate shadow can share one IMDb
    id (it happened: Moonlight, Shogun). The upsert must pick the native,
    same-kind row deterministically instead of raising
    MultipleResultsFound and killing the whole ingest."""
    from sqlalchemy import select

    from app.catalog import omdb_source

    native = Title(tmdb_id=376867, type="movie", name="Moonlight", imdb_id="tt4975722")
    surrogate = Title(tmdb_id=4975722, type="movie", name="Moonlight", imdb_id="tt4975722")
    db_session.add_all([native, surrogate])
    await db_session.flush()

    payload = {
        "imdbID": "tt4975722",
        "Title": "Moonlight",
        "Type": "movie",
        "Year": "2016",
        "Response": "True",
    }
    updated = await omdb_source.upsert_from_omdb(db_session, payload)

    assert updated is not None
    assert updated.tmdb_id == 376867
    assert updated.year == 2016
    # Still exactly two rows: nothing new was created for the pair.
    fetched = await db_session.execute(select(Title).where(Title.imdb_id == "tt4975722"))
    rows = fetched.scalars().all()
    assert len(rows) == 2


async def test_home_streams_the_same_rows_in_order(client, fake_idp, db_session):
    """The streaming endpoint is the same page, one row per line: same
    rows, same order, and the stream fills the cache the full page reads."""
    import json as jsonlib

    await _build_catalog(db_session)
    await do_login(client, fake_idp, LORDO)

    streamed = await client.get("/api/home/stream")
    assert streamed.status_code == 200
    assert streamed.headers["content-type"].startswith("application/x-ndjson")
    lines = [jsonlib.loads(line) for line in streamed.text.splitlines() if line.strip()]
    assert lines, "a populated catalog streams at least one row"

    whole = (await client.get("/api/home")).json()["rows"]
    assert [row["key"] for row in lines] == [row["key"] for row in whole]
