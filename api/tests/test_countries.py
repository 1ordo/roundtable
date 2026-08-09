"""Following more than one country."""

from app.countries import MAX_COUNTRIES, for_user
from app.models import User
from app.notifications.service import _relevant
from tests.util import do_login


def test_the_main_country_stays_first():
    """The first is the one whose age rating gets shown, so order is not
    cosmetic."""
    user = User(username="a", email="a@t", country_code="EG", prefs={"countries": ["FR", "GB"]})
    assert for_user(user) == ["EG", "FR", "GB"]


def test_duplicates_and_junk_are_dropped():
    user = User(
        username="b",
        email="b@t",
        country_code="EG",
        prefs={"countries": ["eg", "FR", "F", "france", "  gb  ", "FR"]},
    )
    # "france" truncates to FR, which is already there.
    assert for_user(user) == ["EG", "FR", "GB"]


def test_no_country_at_all_is_an_empty_list_not_a_guess():
    user = User(username="c", email="c@t", country_code=None, prefs={})
    assert for_user(user) == []


def test_the_list_is_capped():
    user = User(
        username="d",
        email="d@t",
        country_code="EG",
        prefs={"countries": [f"X{chr(65 + i)}" for i in range(20)]},
    )
    assert len(for_user(user)) == MAX_COUNTRIES


def test_availability_alerts_fire_for_every_followed_country():
    user = User(
        username="e",
        email="e@t",
        country_code="EG",
        prefs={"countries": ["FR"]},
        services=[],
    )
    assert _relevant(user, "EG", 8) is True
    assert _relevant(user, "FR", 8) is True, "a second country must count too"
    assert _relevant(user, "US", 8) is False


def test_a_service_filter_still_applies_across_countries():
    user = User(
        username="f",
        email="f@t",
        country_code="EG",
        prefs={"countries": ["FR"]},
        services=[8],
    )
    assert _relevant(user, "FR", 8) is True
    assert _relevant(user, "FR", 119) is False


def test_someone_with_no_country_gets_no_availability_alerts():
    user = User(username="g", email="g@t", country_code=None, prefs={}, services=[])
    assert _relevant(user, "EG", 8) is False


async def test_countries_round_trip_through_the_api(client, fake_idp, db_session):
    from sqlalchemy import select

    await do_login(client, fake_idp, {"sub": "s-cc", "preferred_username": "traveller"})
    csrf = (await client.get("/api/me")).json()["csrf"]
    saved = await client.put(
        "/api/me",
        json={"country_code": "EG", "countries": ["fr", "GB", "FR"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert saved.status_code == 200

    me = (await client.get("/api/me")).json()
    assert me["user"]["countries"] == ["EG", "FR", "GB"]

    user = (await db_session.execute(select(User).where(User.username == "traveller"))).scalar_one()
    await db_session.refresh(user)
    assert user.prefs["countries"] == ["FR", "GB"]
