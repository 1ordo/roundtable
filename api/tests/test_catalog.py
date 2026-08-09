from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.catalog import ingest, omdb
from app.models import Availability, QuotaUsage, Title, User
from tests import fixtures
from tests.util import FRIEND, LORDO, do_login


async def test_home_unauthenticated(client):
    assert (await client.get("/api/home")).status_code == 401


async def test_home_without_key_returns_setup_notice(client, fake_idp):
    await do_login(client, fake_idp, LORDO)
    resp = await client.get("/api/home")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "tmdb_not_configured"


async def test_home_rows_and_cache(client, fake_idp, fake_tmdb_http, db_session):
    await do_login(client, fake_idp, LORDO)

    first = await client.get("/api/home")
    assert first.status_code == 200
    rows = first.json()["rows"]
    assert [r["key"] for r in rows][:2] == ["trending-movies", "trending-tv"]
    # Cards without posters are dropped.
    assert [c["name"] for c in rows[0]["items"]] == ["Coco"]
    calls_after_first = len(fake_tmdb_http)

    second = await client.get("/api/home")
    assert second.status_code == 200
    assert len(fake_tmdb_http) == calls_after_first, "second load must be served from cache"

    used = (
        await db_session.execute(select(QuotaUsage).where(QuotaUsage.source == "tmdb"))
    ).scalar_one()
    assert used.count == calls_after_first


async def test_search_filters_people(client, fake_idp, fake_tmdb_http):
    await do_login(client, fake_idp, LORDO)
    resp = await client.get("/api/search", params={"q": "coco"})
    assert resp.status_code == 200
    names = [r["name"] for r in resp.json()["results"]]
    assert names == ["Coco", "Example Show"]


async def test_title_detail_ingests_and_serves(client, fake_idp, fake_tmdb_http, db_session):
    await do_login(client, fake_idp, LORDO)
    resp = await client.get("/api/titles/movie/354912")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Coco"
    assert body["year"] == 2017
    assert body["keywords"] == ["afterlife", "music"]
    assert body["trailer_youtube_key"] == "xlnPHQ3TLX8"
    assert len(body["cast"]) == 2
    # No countries configured on users yet: fallback country only.
    assert body["countries"] == ["US"]
    assert body["availability"] == {}

    title = (await db_session.execute(select(Title))).scalar_one()
    assert title.tmdb_id == 354912
    assert title.imdb_id == "tt2380307"
    rows = (await db_session.execute(select(Availability))).scalars().all()
    assert {(r.country, r.kind) for r in rows} == {
        ("EG", "stream"),
        ("MA", "stream"),
        ("MA", "rent"),
    }


async def test_title_detail_uses_profile_countries(client, fake_idp, fake_tmdb_http, db_session):
    await do_login(client, fake_idp, LORDO)
    user = (await db_session.execute(select(User))).scalar_one()
    user.country_code = "EG"
    await db_session.commit()

    resp = await client.get("/api/titles/movie/354912")
    body = resp.json()
    assert body["countries"][0] == "EG"
    assert "EG" in body["availability"]
    entry = body["availability"]["EG"][0]
    assert entry["provider_name"] == "Disney Plus"
    assert entry["url"] == "https://www.disneyplus.com/search?q=Coco"


async def test_detail_cached_within_ttl(client, fake_idp, fake_tmdb_http):
    await do_login(client, fake_idp, LORDO)
    await client.get("/api/titles/movie/354912")
    detail_calls = [p for p in fake_tmdb_http if p.startswith("/movie/")]
    await client.get("/api/titles/movie/354912")
    detail_calls_after = [p for p in fake_tmdb_http if p.startswith("/movie/")]
    assert len(detail_calls) == len(detail_calls_after) == 1


async def test_availability_preserves_first_seen(db_session, fake_tmdb_http, tmdb_key):
    title = await ingest.ensure_title(db_session, "movie", 354912)
    await db_session.commit()
    row = (
        await db_session.execute(select(Availability).where(Availability.country == "EG"))
    ).scalar_one()
    original_first_seen = row.first_seen_at

    title.details_refreshed_at = datetime.now(UTC) - timedelta(days=2)
    await db_session.commit()
    await ingest.ensure_title(db_session, "movie", 354912)
    await db_session.commit()

    row2 = (
        await db_session.execute(select(Availability).where(Availability.country == "EG"))
    ).scalar_one()
    assert row2.first_seen_at == original_first_seen
    assert row2.last_seen_at >= row2.first_seen_at


async def test_omdb_scores_and_monthly_policy(db_session, monkeypatch, fake_tmdb_http, tmdb_key):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "omdb_api_key", "omdb-key")

    fetches: list[str] = []

    async def fake_fetch(db, imdb_id):
        fetches.append(imdb_id)
        return fixtures.OMDB_RESPONSE

    monkeypatch.setattr(omdb, "fetch_scores", fake_fetch)

    title = await ingest.ensure_title(db_session, "movie", 354912)
    await omdb.refresh_title_scores(db_session, title)
    assert title.imdb_rating == 8.4
    assert title.rt_score == 97
    assert title.metacritic == 81
    assert len(fetches) == 1

    # Fresh scores: no second call.
    await omdb.refresh_title_scores(db_session, title)
    assert len(fetches) == 1

    # A month later: refresh happens.
    title.scores_refreshed_at = datetime.now(UTC) - timedelta(days=31)
    await omdb.refresh_title_scores(db_session, title)
    assert len(fetches) == 2


async def test_omdb_budget_guard(db_session, monkeypatch):
    from app.catalog import quota
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "omdb_api_key", "omdb-key")
    await quota.bump(db_session, "omdb", get_settings().omdb_daily_budget)

    # At budget: the client must refuse to spend another request.
    result = await omdb.fetch_scores(db_session, "tt2380307")
    assert result is None


async def test_admin_quota_view(client, fake_idp, fake_tmdb_http):
    await do_login(client, fake_idp, LORDO)
    await client.get("/api/home")
    resp = await client.get("/api/admin/quota")
    assert resp.status_code == 200
    body = resp.json()
    assert body["today"].get("tmdb", 0) > 0
    assert body["omdb_daily_budget"] == 900


async def test_member_cannot_read_quota(claimed, client, fake_idp):
    await do_login(client, fake_idp, FRIEND)
    assert (await client.get("/api/admin/quota")).status_code == 403
