import pytest
from sqlalchemy import select

from app.auth import passwords
from app.models import AuditLog, User
from tests.util import FRIEND, LORDO, do_login


async def _enable_password(db_session, registration: bool = False):
    settings = await passwords.get_auth_settings(db_session)
    settings.password_enabled = True
    settings.registration_open = registration
    await db_session.commit()
    return settings


async def _csrf_headers(client) -> dict:
    return {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}


async def test_methods_endpoint_is_public(client, db_session):
    resp = await client.get("/api/auth/methods")
    assert resp.status_code == 200
    body = resp.json()
    assert body["oidc"] is True
    assert set(body) == {"oidc", "password", "registration_open", "first_run"}


async def test_an_empty_instance_offers_a_way_in(client, db_session):
    """A fresh install has no accounts, and the switch that would let you
    make one is behind an admin login. Without this the only working path
    was to edit the database by hand."""
    body = (await client.get("/api/auth/methods")).json()
    assert body["first_run"] is True
    assert body["password"] is True, "the form has to be offered"
    assert body["registration_open"] is True

    made = await client.post(
        "/api/auth/password/register",
        json={"username": "founder", "password": "a-long-enough-password"},
    )
    assert made.status_code == 201, made.text

    after = (await client.get("/api/auth/methods")).json()
    assert after["first_run"] is False, "the door closes behind the first account"
    assert after["registration_open"] is False


async def test_password_login_disabled_by_default(client, db_session):
    resp = await client.post(
        "/api/auth/password/login", json={"username": "Lordo", "password": "whatever"}
    )
    assert resp.status_code == 403


async def test_password_login_and_session(client, fake_idp, db_session):
    await _enable_password(db_session)
    # An OIDC user sets a password, then signs in with it.
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    changed = await client.post(
        "/api/auth/password/change",
        json={"new_password": "correct-horse-battery"},
        headers=headers,
    )
    assert changed.status_code == 204
    await client.post("/api/auth/logout", headers=headers)

    resp = await client.post(
        "/api/auth/password/login",
        json={"username": "lordo", "password": "correct-horse-battery"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"
    me = await client.get("/api/me")
    assert me.json()["user"]["username"] == "Lordo"

    actions = (await db_session.execute(select(AuditLog.action))).scalars().all()
    assert "user.password_change" in actions
    assert "auth.login" in actions


async def test_wrong_password_and_unknown_user_look_identical(client, fake_idp, db_session):
    await _enable_password(db_session)
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    await client.post(
        "/api/auth/password/change",
        json={"new_password": "correct-horse-battery"},
        headers=headers,
    )
    await client.post("/api/auth/logout", headers=headers)

    wrong = await client.post(
        "/api/auth/password/login", json={"username": "Lordo", "password": "not-the-one"}
    )
    unknown = await client.post(
        "/api/auth/password/login", json={"username": "ghost", "password": "not-the-one"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]


async def test_oidc_only_user_cannot_password_login(client, fake_idp, db_session):
    await _enable_password(db_session)
    await do_login(client, fake_idp, FRIEND)
    headers = await _csrf_headers(client)
    await client.post("/api/auth/logout", headers=headers)

    resp = await client.post(
        "/api/auth/password/login", json={"username": "Nadia", "password": "anything-at-all"}
    )
    assert resp.status_code == 401


async def test_disabled_account_cannot_password_login(client, fake_idp, db_session):
    await _enable_password(db_session)
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    await client.post(
        "/api/auth/password/change",
        json={"new_password": "correct-horse-battery"},
        headers=headers,
    )
    await client.post("/api/auth/logout", headers=headers)

    user = (await db_session.execute(select(User))).scalar_one()
    user.is_active = False
    await db_session.commit()

    resp = await client.post(
        "/api/auth/password/login",
        json={"username": "Lordo", "password": "correct-horse-battery"},
    )
    assert resp.status_code == 401


async def test_short_password_rejected(client, fake_idp, db_session):
    await _enable_password(db_session)
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    resp = await client.post(
        "/api/auth/password/change", json={"new_password": "short"}, headers=headers
    )
    assert resp.status_code == 400
    assert "10 characters" in resp.json()["detail"]


async def test_change_requires_current_password(client, fake_idp, db_session):
    await _enable_password(db_session)
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    await client.post(
        "/api/auth/password/change",
        json={"new_password": "first-password-ok"},
        headers=headers,
    )

    without = await client.post(
        "/api/auth/password/change",
        json={"new_password": "second-password-ok"},
        headers=headers,
    )
    assert without.status_code == 400

    wrong = await client.post(
        "/api/auth/password/change",
        json={"current_password": "nope-nope-nope", "new_password": "second-password-ok"},
        headers=headers,
    )
    assert wrong.status_code == 401

    right = await client.post(
        "/api/auth/password/change",
        json={"current_password": "first-password-ok", "new_password": "second-password-ok"},
        headers=headers,
    )
    assert right.status_code == 204


async def test_registration_closed_by_default(claimed, client, db_session):
    await _enable_password(db_session, registration=False)
    resp = await client.post(
        "/api/auth/password/register",
        json={"username": "newcomer", "password": "a-good-long-password"},
    )
    assert resp.status_code == 400


async def test_first_registered_user_is_admin(client, db_session):
    await _enable_password(db_session, registration=True)
    first = await client.post(
        "/api/auth/password/register",
        json={"username": "founder", "password": "a-good-long-password"},
    )
    assert first.status_code == 201
    assert first.json()["role"] == "admin"

    second = await client.post(
        "/api/auth/password/register",
        json={"username": "friend", "password": "another-long-password"},
    )
    assert second.json()["role"] == "member"

    taken = await client.post(
        "/api/auth/password/register",
        json={"username": "FOUNDER", "password": "yet-another-password"},
    )
    assert taken.status_code == 400


async def test_admin_can_toggle_methods_but_not_disable_both(client, fake_idp, db_session):
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)

    current = (await client.get("/api/admin/settings/auth")).json()
    assert current["oidc_enabled"] is True

    both_off = await client.put(
        "/api/admin/settings/auth",
        json={"oidc_enabled": False, "password_enabled": False, "registration_open": False},
        headers=headers,
    )
    assert both_off.status_code == 400

    enabled = await client.put(
        "/api/admin/settings/auth",
        json={"oidc_enabled": True, "password_enabled": True, "registration_open": True},
        headers=headers,
    )
    assert enabled.status_code == 200
    assert enabled.json()["password_enabled"] is True

    methods = (await client.get("/api/auth/methods")).json()
    assert methods["password"] is True
    assert methods["registration_open"] is True

    actions = (await db_session.execute(select(AuditLog.action))).scalars().all()
    assert "settings.auth_update" in actions


async def test_cannot_disable_oidc_without_own_password(client, fake_idp, db_session):
    """An admin who signed in with a passkey and has no password must not be
    able to switch passkeys off and lock themselves out."""
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    resp = await client.put(
        "/api/admin/settings/auth",
        json={"oidc_enabled": False, "password_enabled": True, "registration_open": False},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "lock yourself out" in resp.json()["detail"]


async def test_disabling_oidc_blocks_that_route(client, fake_idp, db_session):
    await _enable_password(db_session)
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    # Set a password first, which is exactly what the guard above demands.
    await client.post(
        "/api/auth/password/change",
        json={"new_password": "my-own-password-here"},
        headers=headers,
    )
    # Someone starts a passkey sign-in while it is still on.
    from urllib.parse import parse_qs, urlparse

    fake_idp.claims = LORDO
    started = await client.get("/auth/login")
    state = parse_qs(urlparse(started.headers["location"]).query)["state"][0]

    switched = await client.put(
        "/api/admin/settings/auth",
        json={"oidc_enabled": False, "password_enabled": True, "registration_open": False},
        headers=headers,
    )
    assert switched.status_code == 200

    resp = await client.get("/auth/login")
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login?error=oidc_disabled"

    # The half-finished flow in the other tab is refused as well.
    callback = await client.get(f"/auth/callback?code=fake-code&state={state}")
    assert callback.headers["location"] == "/login?error=oidc_disabled"


async def test_member_cannot_change_auth_settings(claimed, client, fake_idp, db_session):
    await do_login(client, fake_idp, FRIEND)
    headers = await _csrf_headers(client)
    resp = await client.put(
        "/api/admin/settings/auth",
        json={"oidc_enabled": True, "password_enabled": True, "registration_open": False},
        headers=headers,
    )
    assert resp.status_code == 403


async def test_admin_sets_another_users_password(client, fake_idp, db_session):
    await _enable_password(db_session)
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    created = await client.post("/api/admin/users", json={"username": "nadia"}, headers=headers)
    nadia_id = created.json()["id"]

    resp = await client.put(
        f"/api/admin/users/{nadia_id}/password",
        json={"password": "a-password-for-her"},
        headers=headers,
    )
    assert resp.status_code == 204
    await client.post("/api/auth/logout", headers=headers)

    login = await client.post(
        "/api/auth/password/login",
        json={"username": "nadia", "password": "a-password-for-her"},
    )
    assert login.status_code == 200

    actions = (await db_session.execute(select(AuditLog.action))).scalars().all()
    assert "user.password_set" in actions


async def test_rate_limit_blocks_repeated_failures(client, db_session, monkeypatch):
    await _enable_password(db_session)
    attempts = {"count": 0}

    async def fake_too_many(username):
        return attempts["count"] >= passwords.MAX_ATTEMPTS

    async def fake_record(username):
        attempts["count"] += 1

    monkeypatch.setattr(passwords, "too_many_attempts", fake_too_many)
    monkeypatch.setattr(passwords, "record_failure", fake_record)

    for _ in range(passwords.MAX_ATTEMPTS):
        resp = await client.post(
            "/api/auth/password/login", json={"username": "Lordo", "password": "wrong"}
        )
        assert resp.status_code == 401

    blocked = await client.post(
        "/api/auth/password/login", json={"username": "Lordo", "password": "wrong"}
    )
    assert blocked.status_code == 429


def test_username_and_password_validation():
    with pytest.raises(passwords.PasswordError):
        passwords.validate_username("a")
    with pytest.raises(passwords.PasswordError):
        passwords.validate_username("has spaces")
    with pytest.raises(passwords.PasswordError):
        passwords.validate_username("-startswithdash")
    assert passwords.validate_username("Lordo_1.x") == "Lordo_1.x"

    with pytest.raises(passwords.PasswordError):
        passwords.validate_password("           ")
    assert passwords.validate_password("a-fine-password")


def test_hashes_are_salted_and_verifiable():
    one = passwords.hash_password("the-same-password")
    two = passwords.hash_password("the-same-password")
    assert one != two, "argon2 salts every hash"
    assert one.startswith("$argon2")
    assert passwords.hasher.verify(one, "the-same-password")
