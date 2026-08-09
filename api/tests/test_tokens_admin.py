from sqlalchemy import select

from app.models import AuditLog, User
from tests.util import FRIEND, LORDO, do_login


async def _csrf_headers(client) -> dict:
    return {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}


async def _enable_api_for(client, headers, username: str) -> None:
    """Admin flips the global flag and the per-user switch."""
    await client.put("/api/admin/flags/api_tokens", json={"enabled": True}, headers=headers)
    users = (await client.get("/api/admin/users")).json()
    target = next(u for u in users if u["username"] == username)
    await client.patch(
        f"/api/admin/users/{target['id']}", json={"api_enabled": True}, headers=headers
    )


async def test_tokens_gated_by_flag_and_user(client, fake_idp):
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)

    resp = await client.post("/api/tokens", json={"name": "cli", "scope": "read"}, headers=headers)
    assert resp.status_code == 403  # global flag off

    await client.put("/api/admin/flags/api_tokens", json={"enabled": True}, headers=headers)
    resp = await client.post("/api/tokens", json={"name": "cli", "scope": "read"}, headers=headers)
    assert resp.status_code == 403  # per-user switch still off


async def test_token_lifecycle_and_bearer_auth(client, fake_idp, db_session):
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    await _enable_api_for(client, headers, "Lordo")

    created = await client.post(
        "/api/tokens", json={"name": "claude", "scope": "read"}, headers=headers
    )
    assert created.status_code == 201
    plaintext = created.json()["token"]
    token_id = created.json()["info"]["id"]
    assert plaintext.startswith("wdk_")

    # Bearer works without any cookies.
    bare = await client.get("/api/lists", headers={"Authorization": f"Bearer {plaintext}"})
    assert bare.status_code == 200

    # Read-only scope rejects writes.
    write_attempt = await client.post(
        "/api/lists",
        json={"name": "Nope"},
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert write_attempt.status_code == 403

    # Revoke, then the token is dead.
    revoke = await client.delete(f"/api/tokens/{token_id}", headers=headers)
    assert revoke.status_code == 204
    dead = await client.get("/api/lists", headers={"Authorization": f"Bearer {plaintext}"})
    assert dead.status_code == 401

    actions = (await db_session.execute(select(AuditLog.action))).scalars().all()
    for expected in ("token.create", "token.use", "token.revoke", "flags.update"):
        assert expected in actions


async def test_write_token_can_write(client, fake_idp):
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    await _enable_api_for(client, headers, "Lordo")
    created = await client.post(
        "/api/tokens", json={"name": "rw", "scope": "write"}, headers=headers
    )
    plaintext = created.json()["token"]
    resp = await client.post(
        "/api/lists",
        json={"name": "Via API"},
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert resp.status_code == 201


async def test_member_cannot_manage_admin_surfaces(claimed, client, fake_idp):
    await do_login(client, fake_idp, FRIEND)
    headers = await _csrf_headers(client)
    assert (await client.get("/api/admin/users")).status_code == 403
    assert (
        await client.put("/api/admin/flags/api_tokens", json={"enabled": True}, headers=headers)
    ).status_code == 403


async def test_admin_user_management(client, fake_idp, db_session):
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)

    created = await client.post(
        "/api/admin/users",
        json={"username": "guest", "email": "guest@example.com"},
        headers=headers,
    )
    assert created.status_code == 201
    guest_id = created.json()["id"]
    assert created.json()["has_oidc"] is False

    dup = await client.post("/api/admin/users", json={"username": "GUEST"}, headers=headers)
    assert dup.status_code == 409

    disabled = await client.patch(
        f"/api/admin/users/{guest_id}", json={"is_active": False}, headers=headers
    )
    assert disabled.json()["is_active"] is False

    me_id = next(
        u["id"] for u in (await client.get("/api/admin/users")).json() if u["username"] == "Lordo"
    )
    self_disable = await client.patch(
        f"/api/admin/users/{me_id}", json={"is_active": False}, headers=headers
    )
    assert self_disable.status_code == 400
    self_demote = await client.patch(
        f"/api/admin/users/{me_id}", json={"role": "member"}, headers=headers
    )
    assert self_demote.status_code == 400

    actions = (await db_session.execute(select(AuditLog.action))).scalars().all()
    assert "user.create" in actions
    assert "user.update" in actions


async def test_disabled_user_session_is_rejected(client, fake_idp, db_session):
    await do_login(client, fake_idp, FRIEND)
    nadia_headers = await _csrf_headers(client)
    assert (await client.get("/api/me")).status_code == 200

    user = (await db_session.execute(select(User).where(User.username == "Nadia"))).scalar_one()
    user.is_active = False
    await db_session.commit()

    assert (await client.get("/api/lists", headers=nadia_headers)).status_code == 401


async def test_stats_endpoint(client, fake_idp, fake_tmdb_http):
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    await client.post(
        "/api/history",
        json={"type": "movie", "tmdb_id": 354912, "rating_10": 9, "loved": True},
        headers=headers,
    )
    resp = await client.get("/api/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["totals"]["watched"] == 1
    assert body["totals"]["hours"] == 1.8  # 105 minutes
    assert body["totals"]["loved"] == 1
    assert body["genres"][0]["name"] in ("Animation", "Family")
    assert body["streak_longest"] == 1
    assert body["wrap"]["favorite"] == "Coco"
    assert any(a["name"] == "Anthony Gonzalez" for a in body["top_actors"])


async def test_mcp_mount_exists(client, fake_idp):
    await do_login(client, fake_idp, LORDO)
    # The MCP endpoint speaks the MCP protocol, not plain GET; any response
    # that is not a 404 proves the mount is alive.
    resp = await client.get("/api/mcp/")
    assert resp.status_code != 404
