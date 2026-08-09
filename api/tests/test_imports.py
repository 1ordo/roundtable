import pytest
from sqlalchemy import select

from app.imports import parsers
from app.imports.matcher import match_row
from app.models import ImportBatch, ListItem, WatchEvent
from tests.util import LORDO, do_login

NETFLIX_HISTORY_CSV = """Title,Date
"Coco","01/15/24"
"Example Show: Season 1: Chapter One: The Vanishing","02/01/24"
"Example Show: Season 1: Chapter Two: The Weirdo","02/02/24"
"Some Unknown Thing XYZQ","03/01/24"
"""

NETFLIX_MYLIST_CSV = """Profile Name,Title Name,Country,Utc Title Add Date
Lordo,"Coco",EG,2024-01-01
Lordo,"Example Show: Season 1",EG,2024-01-02
"""


def test_split_netflix_title():
    assert parsers.split_netflix_title("Coco") == ("Coco", None)
    assert parsers.split_netflix_title("Show: Season 2: Ep") == ("Show", "tv")
    assert parsers.split_netflix_title("Show: Limited Series: Ep") == ("Show", "tv")
    assert parsers.split_netflix_title("Show: Part 1: Ep") == ("Show", "tv")
    # Two-colon rows without a marker still read as series episodes.
    assert parsers.split_netflix_title("Show: Book One: Water") == ("Show", "tv")
    # A single colon with no marker stays a movie title.
    assert parsers.split_netflix_title("Mission: Impossible") == ("Mission: Impossible", None)


def test_parse_netflix_history():
    rows = parsers.parse_netflix_history(NETFLIX_HISTORY_CSV)
    assert len(rows) == 4
    assert rows[0]["name"] == "Coco"
    assert rows[0]["watched_at"] == "2024-01-15"
    assert rows[1]["name"] == "Example Show"
    assert rows[1]["type_hint"] == "tv"


def test_parse_netflix_history_rejects_garbage():
    with pytest.raises(parsers.ImportParseError):
        parsers.parse_netflix_history("nope,nothing\n1,2\n")


def test_parse_json_payload():
    rows = parsers.parse_json_payload('[{"title": "Coco", "year": 2017, "type": "movie"}]')
    assert rows[0]["year"] == 2017
    with pytest.raises(parsers.ImportParseError):
        parsers.parse_json_payload("{}")
    with pytest.raises(parsers.ImportParseError):
        parsers.parse_json_payload("not json")


async def test_match_row_rules(db_session, fake_tmdb_http):
    # Exact single name match: auto.
    status, candidates = await match_row(db_session, "Coco", "movie", None)
    assert status == "matched"
    assert candidates[0]["tmdb_id"] == 354912

    # Type hint filters the multi results.
    status, candidates = await match_row(db_session, "Example Show", "tv", None)
    assert status == "matched"
    assert candidates[0]["type"] == "tv"


@pytest.fixture
def inline_queue(monkeypatch):
    """Run the worker job inline instead of enqueueing to Redis."""
    import uuid as uuid_module

    from app.db import get_sessionmaker
    from app.imports import queue
    from app.imports.service import process_batch

    async def _inline(batch_id):
        async with get_sessionmaker()() as db:
            await process_batch(db, uuid_module.UUID(str(batch_id)))

    monkeypatch.setattr(queue, "enqueue_process_batch", _inline)


async def _csrf_headers(client) -> dict:
    return {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}


async def test_history_import_end_to_end(
    client, fake_idp, fake_tmdb_http, inline_queue, db_session
):
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)

    resp = await client.post(
        "/api/imports",
        data={"service": "netflix_history"},
        files={"file": ("history.csv", NETFLIX_HISTORY_CSV.encode(), "text/csv")},
        headers=headers,
    )
    assert resp.status_code == 201
    batch_id = resp.json()["id"]

    detail = (await client.get(f"/api/imports/{batch_id}", headers=headers)).json()
    assert detail["status"] in ("done", "review")
    stats = detail["stats"]
    # Coco once, the show twice (two episodes -> two watch events), one unknown.
    assert stats["imported"] == 3
    assert stats["unmatched"] == 1

    events = (await db_session.execute(select(WatchEvent))).scalars().all()
    assert len(events) == 3
    assert all(e.source == "import" for e in events)

    history = (await client.get("/api/history", headers=headers)).json()
    assert history["total"] == 3


async def test_mylist_import_lands_in_watchlist(
    client, fake_idp, fake_tmdb_http, inline_queue, db_session
):
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)

    resp = await client.post(
        "/api/imports",
        data={"service": "netflix_mylist"},
        files={"file": ("MyList.csv", NETFLIX_MYLIST_CSV.encode(), "text/csv")},
        headers=headers,
    )
    assert resp.status_code == 201

    items = (await db_session.execute(select(ListItem))).scalars().all()
    assert len(items) == 2


async def test_import_dedupes_history(client, fake_idp, fake_tmdb_http, inline_queue, db_session):
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    for _ in range(2):
        await client.post(
            "/api/imports",
            data={"service": "netflix_history"},
            files={"file": ("history.csv", NETFLIX_HISTORY_CSV.encode(), "text/csv")},
            headers=headers,
        )
    events = (await db_session.execute(select(WatchEvent))).scalars().all()
    assert len(events) == 3, "second import of the same file must not duplicate"


async def test_review_queue_resolution(
    client, fake_idp, fake_tmdb_http, inline_queue, db_session, monkeypatch
):
    from app.imports import service as import_service

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
    resp = await client.post(
        "/api/imports",
        data={"service": "json", "target": "watchlist", "payload": '[{"title": "Coco"}]'},
        headers=headers,
    )
    assert resp.status_code == 201
    batch_id = resp.json()["id"]

    detail = (await client.get(f"/api/imports/{batch_id}", headers=headers)).json()
    assert detail["status"] == "review"
    assert detail["pending_review"] == 1
    entry = detail["review_queue"][0]
    assert len(entry["candidates"]) == 2

    resolved = await client.post(
        f"/api/imports/{batch_id}/resolve",
        json={"index": entry["index"], "tmdb_id": 354912, "type": "movie"},
        headers=headers,
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "done"

    items = (await db_session.execute(select(ListItem))).scalars().all()
    assert len(items) == 1

    batch = (await db_session.execute(select(ImportBatch))).scalar_one()
    assert batch.stats["imported"] == 1
    assert batch.stats["ambiguous"] == 0


async def test_import_isolated_per_user(client, fake_idp, fake_tmdb_http, inline_queue):
    from tests.util import FRIEND

    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    resp = await client.post(
        "/api/imports",
        data={"service": "json", "payload": '[{"title": "Coco", "type": "movie"}]'},
        headers=headers,
    )
    batch_id = resp.json()["id"]
    await client.post("/api/auth/logout", headers=headers)

    await do_login(client, fake_idp, FRIEND)
    headers2 = await _csrf_headers(client)
    assert (await client.get(f"/api/imports/{batch_id}", headers=headers2)).status_code == 404
    assert (await client.get("/api/imports", headers=headers2)).json() == []
