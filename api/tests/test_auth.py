from sqlalchemy import select

from app.models import AuditLog, User
from tests.util import FRIEND, LORDO, do_login


async def test_login_redirects_to_idp(client, fake_idp):
    resp = await client.get("/auth/login")
    assert resp.status_code == 302
    assert resp.headers["location"].startswith("https://idp.test/authorize")
    assert "wd_preauth" in resp.cookies


async def test_full_login_bootstraps_admin(client, fake_idp, db_session):
    resp = await do_login(client, fake_idp, LORDO)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/app"
    assert "wd_session" in resp.cookies

    me = await client.get("/api/me")
    assert me.status_code == 200
    body = me.json()
    assert body["user"]["username"] == "Lordo"
    assert body["user"]["role"] == "admin"
    assert body["csrf"]

    actions = (await db_session.execute(select(AuditLog.action))).scalars().all()
    assert "auth.login" in actions


async def test_unknown_identity_becomes_member(claimed, client, fake_idp):
    await do_login(client, fake_idp, FRIEND)
    me = await client.get("/api/me")
    assert me.json()["user"]["role"] == "member"


async def test_relogin_reuses_user(client, fake_idp, db_session):
    await do_login(client, fake_idp, FRIEND)
    await client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]},
    )
    await do_login(client, fake_idp, FRIEND)
    users = (await db_session.execute(select(User))).scalars().all()
    assert len(users) == 1


async def test_disabled_user_denied(client, fake_idp, db_session):
    await do_login(client, fake_idp, FRIEND)
    user = (await db_session.execute(select(User))).scalar_one()
    user.is_active = False
    await db_session.commit()

    fresh = await do_login(client, fake_idp, FRIEND)
    assert fresh.headers["location"] == "/login?error=denied"

    actions = (await db_session.execute(select(AuditLog.action))).scalars().all()
    assert "auth.denied" in actions


async def test_state_mismatch_rejected(client, fake_idp):
    await client.get("/auth/login")
    resp = await client.get("/auth/callback?code=x&state=wrong-state")
    assert resp.headers["location"] == "/login?error=state_mismatch"


async def test_oidc_failure_audited(client, fake_idp, db_session):
    fake_idp.fail_exchange = True
    resp = await do_login(client, fake_idp, LORDO)
    assert resp.headers["location"] == "/login?error=oidc_failed"
    actions = (await db_session.execute(select(AuditLog.action))).scalars().all()
    assert "auth.failed" in actions


async def test_me_requires_session(client):
    resp = await client.get("/api/me")
    assert resp.status_code == 401


async def test_open_redirect_blocked(client, fake_idp):
    fake_idp.claims = LORDO
    login_resp = await client.get("/auth/login?next=https://evil.example")
    from urllib.parse import parse_qs, urlparse

    state = parse_qs(urlparse(login_resp.headers["location"]).query)["state"][0]
    resp = await client.get(f"/auth/callback?code=c&state={state}")
    assert resp.headers["location"] == "/app"


async def test_logout_requires_csrf_and_revokes(client, fake_idp, db_session):
    await do_login(client, fake_idp, LORDO)

    no_csrf = await client.post("/api/auth/logout")
    assert no_csrf.status_code == 403

    csrf = (await client.get("/api/me")).json()["csrf"]
    resp = await client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 204

    after = await client.get("/api/me")
    assert after.status_code == 401

    actions = (await db_session.execute(select(AuditLog.action))).scalars().all()
    assert "auth.logout" in actions
