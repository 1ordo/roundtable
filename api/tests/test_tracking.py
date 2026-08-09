from sqlalchemy import select

from app.models import AuditLog, List, WatchEvent
from tests.util import FRIEND, LORDO, do_login


async def _csrf(client) -> dict[str, str]:
    me = await client.get("/api/me")
    return {"X-CSRF-Token": me.json()["csrf"]}


async def _login_with_csrf(client, fake_idp, claims) -> dict[str, str]:
    await do_login(client, fake_idp, claims)
    return await _csrf(client)


async def test_lists_bootstrap(client, fake_idp):
    headers = await _login_with_csrf(client, fake_idp, LORDO)
    resp = await client.get("/api/lists", headers=headers)
    assert resp.status_code == 200
    kinds = {lst["kind"] for lst in resp.json()["lists"]}
    assert kinds == {"watchlist", "shared"}


async def test_shared_list_is_shared(client, fake_idp, db_session):
    await _login_with_csrf(client, fake_idp, LORDO)
    await client.post("/api/auth/logout", headers=await _csrf(client))
    headers = await _login_with_csrf(client, fake_idp, FRIEND)
    resp = await client.get("/api/lists", headers=headers)
    shared = [lst for lst in resp.json()["lists"] if lst["kind"] == "shared"]
    assert len(shared) == 1
    total_shared = (
        (await db_session.execute(select(List).where(List.kind == "shared"))).scalars().all()
    )
    assert len(total_shared) == 1, "both users must see the same shared list"


async def test_add_and_remove_watchlist_item(client, fake_idp, fake_tmdb_http):
    headers = await _login_with_csrf(client, fake_idp, LORDO)
    lists = (await client.get("/api/lists", headers=headers)).json()["lists"]
    watchlist_id = next(lst["id"] for lst in lists if lst["kind"] == "watchlist")

    add = await client.post(
        f"/api/lists/{watchlist_id}/items",
        json={"type": "movie", "tmdb_id": 354912},
        headers=headers,
    )
    assert add.status_code == 201

    again = await client.post(
        f"/api/lists/{watchlist_id}/items",
        json={"type": "movie", "tmdb_id": 354912},
        headers=headers,
    )
    assert again.status_code == 201

    items = (await client.get(f"/api/lists/{watchlist_id}/items", headers=headers)).json()
    assert len(items["items"]) == 1
    assert items["items"][0]["title"]["name"] == "Coco"
    assert items["items"][0]["added_by"] == "Lordo"

    state = (await client.get("/api/titles/movie/354912/state", headers=headers)).json()
    assert watchlist_id in state["lists"]

    remove = await client.delete(f"/api/lists/{watchlist_id}/items/movie/354912", headers=headers)
    assert remove.status_code == 204
    items = (await client.get(f"/api/lists/{watchlist_id}/items", headers=headers)).json()
    assert items["items"] == []


async def test_other_users_private_list_hidden(client, fake_idp):
    headers = await _login_with_csrf(client, fake_idp, LORDO)
    created = await client.post("/api/lists", json={"name": "Mine"}, headers=headers)
    private_id = created.json()["id"]
    await client.post("/api/auth/logout", headers=await _csrf(client))

    headers2 = await _login_with_csrf(client, fake_idp, FRIEND)
    resp = await client.get(f"/api/lists/{private_id}/items", headers=headers2)
    assert resp.status_code == 404


async def test_delete_only_custom_lists(client, fake_idp):
    headers = await _login_with_csrf(client, fake_idp, LORDO)
    lists = (await client.get("/api/lists", headers=headers)).json()["lists"]
    watchlist_id = next(lst["id"] for lst in lists if lst["kind"] == "watchlist")
    assert (await client.delete(f"/api/lists/{watchlist_id}", headers=headers)).status_code == 400

    created = await client.post("/api/lists", json={"name": "Temp"}, headers=headers)
    assert (
        await client.delete(f"/api/lists/{created.json()['id']}", headers=headers)
    ).status_code == 204


async def test_watch_history_flow(client, fake_idp, fake_tmdb_http):
    headers = await _login_with_csrf(client, fake_idp, LORDO)

    marked = await client.post(
        "/api/history",
        json={"type": "movie", "tmdb_id": 354912, "rating_10": 9, "loved": True},
        headers=headers,
    )
    assert marked.status_code == 201
    event = marked.json()
    assert event["rating_10"] == 9
    assert event["loved"] is True

    bad = await client.post(
        "/api/history",
        json={"type": "movie", "tmdb_id": 354912, "rating_10": 11},
        headers=headers,
    )
    assert bad.status_code == 422

    page = (await client.get("/api/history", headers=headers)).json()
    assert page["total"] == 1

    updated = await client.patch(
        f"/api/history/{event['id']}", json={"rating_10": 7}, headers=headers
    )
    assert updated.json()["rating_10"] == 7

    state = (await client.get("/api/titles/movie/354912/state", headers=headers)).json()
    assert state["watched_count"] == 1
    assert state["my_rating"] == 7
    assert state["loved"] is True

    assert (await client.delete(f"/api/history/{event['id']}", headers=headers)).status_code == 204
    assert (await client.get("/api/history", headers=headers)).json()["total"] == 0


async def test_history_is_private(client, fake_idp, fake_tmdb_http, db_session):
    headers = await _login_with_csrf(client, fake_idp, LORDO)
    await client.post("/api/history", json={"type": "movie", "tmdb_id": 354912}, headers=headers)
    await client.post("/api/auth/logout", headers=await _csrf(client))

    headers2 = await _login_with_csrf(client, fake_idp, FRIEND)
    assert (await client.get("/api/history", headers=headers2)).json()["total"] == 0
    lordo_event = (await db_session.execute(select(WatchEvent))).scalar_one()
    resp = await client.patch(
        f"/api/history/{lordo_event.id}", json={"rating_10": 1}, headers=headers2
    )
    assert resp.status_code == 404


async def test_update_profile_and_audit(client, fake_idp, db_session):
    headers = await _login_with_csrf(client, fake_idp, LORDO)
    resp = await client.put(
        "/api/me", json={"country_code": "eg", "services": [8, 337]}, headers=headers
    )
    assert resp.status_code == 200
    me = (await client.get("/api/me")).json()
    assert me["user"]["country_code"] == "EG"
    assert me["user"]["services"] == [8, 337]
    actions = (await db_session.execute(select(AuditLog.action))).scalars().all()
    assert "user.update_profile" in actions


async def test_avatar_upload_strips_metadata(client, fake_idp, tmp_path, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path))
    headers = await _login_with_csrf(client, fake_idp, LORDO)

    import io

    from PIL import Image

    img = Image.new("RGB", (900, 700), (200, 120, 40))
    exif = img.getexif()
    exif[0x010F] = "SecretCamera"
    buffer = io.BytesIO()
    img.save(buffer, "JPEG", exif=exif)

    resp = await client.post(
        "/api/me/avatar",
        files={"file": ("me.jpg", buffer.getvalue(), "image/jpeg")},
        headers=headers,
    )
    assert resp.status_code == 200
    path = resp.json()["avatar_path"]
    assert path.endswith(".webp")

    served = await client.get(path)
    assert served.status_code == 200
    stored = Image.open(io.BytesIO(served.content))
    assert stored.size[0] <= 512 and stored.size[1] <= 512
    assert not stored.getexif(), "EXIF must be stripped"

    bad = await client.post(
        "/api/me/avatar",
        files={"file": ("evil.svg", b"<svg onload=alert(1)>", "image/svg+xml")},
        headers=headers,
    )
    assert bad.status_code == 400


async def test_avatar_serving_blocks_traversal(client, fake_idp):
    await _login_with_csrf(client, fake_idp, LORDO)
    resp = await client.get("/api/media/avatars/..%2Fsecrets.webp")
    assert resp.status_code == 404


async def test_exports(client, fake_idp, fake_tmdb_http, db_session):
    headers = await _login_with_csrf(client, fake_idp, LORDO)
    await client.post(
        "/api/history",
        json={"type": "movie", "tmdb_id": 354912, "rating_10": 8},
        headers=headers,
    )

    csv_resp = await client.get("/api/export/history.csv")
    assert csv_resp.status_code == 200
    assert "Coco" in csv_resp.text
    assert "rating_10" in csv_resp.text

    json_resp = await client.get("/api/export/all.json")
    body = json_resp.json()
    assert body["user"]["username"] == "Lordo"
    assert len(body["history"]) == 1

    actions = (await db_session.execute(select(AuditLog.action))).scalars().all()
    assert "export.history" in actions
    assert "export.all" in actions


async def test_watch_requires_csrf(client, fake_idp, fake_tmdb_http):
    await do_login(client, fake_idp, LORDO)
    resp = await client.post("/api/history", json={"type": "movie", "tmdb_id": 354912})
    assert resp.status_code == 403
