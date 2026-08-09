"""The local development sign-in must be impossible to reach outside a
development environment."""

import pytest

from app.auth.dev import DevLoginNotAllowed, assert_safe_configuration, dev_login_user
from app.config import get_settings


@pytest.fixture
def dev_mode(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "env", "dev")
    monkeypatch.setattr(settings, "dev_login", True)
    return settings


async def test_dev_login_disabled_by_default(client, db_session):
    settings = get_settings()
    assert settings.env == "test"
    assert settings.dev_login is False
    assert settings.dev_login_enabled is False
    with pytest.raises(DevLoginNotAllowed):
        await dev_login_user(db_session, "Lordo")


async def test_dev_login_requires_dev_env(monkeypatch, db_session):
    settings = get_settings()
    # The flag alone is not enough: the environment must also be dev.
    monkeypatch.setattr(settings, "dev_login", True)
    monkeypatch.setattr(settings, "env", "prod")
    assert settings.dev_login_enabled is False
    with pytest.raises(DevLoginNotAllowed):
        await dev_login_user(db_session, "Lordo")


async def test_startup_refuses_dev_login_in_production(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "dev_login", True)
    monkeypatch.setattr(settings, "env", "prod")
    with pytest.raises(RuntimeError, match="Refusing to start"):
        assert_safe_configuration()

    monkeypatch.setattr(settings, "env", "dev")
    assert_safe_configuration()  # allowed in development


async def test_dev_login_signs_in_and_switches_user(client, dev_mode):
    resp = await client.get("/auth/login")
    assert resp.status_code == 302
    assert resp.headers["location"] == "/app"
    me = (await client.get("/api/me")).json()
    assert me["user"]["username"] == "Lordo"
    assert me["user"]["role"] == "admin"

    switched = await client.get("/auth/login?as=Nadia")
    assert switched.status_code == 302
    me = (await client.get("/api/me")).json()
    assert me["user"]["username"] == "Nadia"
    assert me["user"]["role"] == "member"


async def test_dev_login_still_blocks_open_redirect(client, dev_mode):
    resp = await client.get("/auth/login?next=https://evil.example")
    assert resp.headers["location"] == "/app"
