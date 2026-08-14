"""Which countries a title page reports availability for.

Written against a real failure. Somebody in Egypt who had added Britain and
the United States under "extra countries" opened a Marvel film and saw only
Apple TV rent and buy. Every one of those films was in the table marked
Disney Plus under GB and under US; the page had never asked for those rows.

It had asked for Egypt plus Morocco, because Morocco is where another
account on the instance lives. So the page was showing a stranger's country
and hiding the two the person had chosen, which is wrong in both directions
at once, and quietly tells you something about the other account as well.

The settings page has always promised the opposite: "availability, cinema
listings and release alerts all widen to cover these".
"""

from sqlalchemy import select

from app.models import Availability, Title, User
from app.routers.catalog import _where_they_watch
from tests.util import LORDO, do_login


async def a_marvel_film(db) -> Title:
    film = Title(tmdb_id=1726, type="movie", name="Iron Man", year=2008)
    db.add(film)
    await db.flush()
    for country, provider, kind in (
        ("EG", "Apple TV Store", "rent"),
        ("EG", "Apple TV Store", "buy"),
        ("GB", "Disney Plus", "stream"),
        ("US", "Disney Plus", "stream"),
        ("MA", "Shahid", "stream"),
    ):
        db.add(
            Availability(
                title_id=film.id,
                country=country,
                provider_id=abs(hash((country, provider))) % 10_000,
                provider_name=provider,
                kind=kind,
            )
        )
    await db.flush()
    return film


class TestTheCountriesAsked:
    async def test_the_extra_countries_someone_chose_are_the_ones_used(
        self, client, fake_idp, db_session
    ):
        await do_login(client, fake_idp, LORDO)
        me = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
        me.country_code = "EG"
        me.prefs = {"countries": ["GB", "US"]}
        await db_session.commit()

        assert _where_they_watch(me) == ["EG", "GB", "US"]

    async def test_another_accounts_country_is_not_one_of_them(self, client, fake_idp, db_session):
        """The page used to add every other user's country. Morocco is not
        your country because somebody else on the box lives there."""
        await do_login(client, fake_idp, LORDO)
        me = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
        me.country_code = "EG"
        me.prefs = {}
        await db_session.commit()

        from app.models import Tenant

        tenant = (await db_session.execute(select(Tenant))).scalars().first()
        db_session.add(
            User(tenant_id=tenant.id, username="someone_ma", email="ma@test", country_code="MA")
        )
        await db_session.commit()

        assert _where_they_watch(me) == ["EG"]

    async def test_someone_who_set_nothing_gets_the_instance_default(
        self, client, fake_idp, db_session
    ):
        await do_login(client, fake_idp, LORDO)
        me = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
        me.country_code = None
        me.prefs = {}
        await db_session.commit()

        from app.config import get_settings

        assert _where_they_watch(me) == [get_settings().default_country]

    async def test_the_title_page_reports_disney_from_the_added_countries(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key
    ):
        """The whole bug, end to end: the rows existed and never came back."""
        await do_login(client, fake_idp, LORDO)
        me = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
        me.country_code = "EG"
        me.prefs = {"countries": ["GB", "US"]}
        await a_marvel_film(db_session)
        await db_session.commit()

        resp = await client.get("/api/titles/movie/1726")
        assert resp.status_code == 200, resp.text
        availability = resp.json()["availability"]

        assert set(availability) == {"EG", "GB", "US"}, "their countries, and only theirs"
        assert "Disney Plus" in [p["provider_name"] for p in availability["GB"]]
        assert "Disney Plus" in [p["provider_name"] for p in availability["US"]]
        assert "MA" not in availability, "another account's country is not yours"


class TestTheFallbackIsARealCountry:
    """An environment variable set to nothing means unset, not "".

    compose shipped RT_DEFAULT_COUNTRY: ${RT_DEFAULT_COUNTRY:-}, so every
    instance whose operator had not chosen one ran with default_country
    equal to the empty string. Anybody who had not set a country on their
    profile was then looked up with `country IN ('')` and saw no
    availability at all, anywhere, without anything saying so.
    """

    def test_a_blank_environment_value_does_not_become_a_country(self, monkeypatch):
        from app.config import Settings

        monkeypatch.setenv("RT_DEFAULT_COUNTRY", "")
        assert Settings().default_country == "US"

    def test_whitespace_is_not_a_country_either(self, monkeypatch):
        from app.config import Settings

        monkeypatch.setenv("RT_DEFAULT_COUNTRY", "   ")
        assert Settings().default_country == "US"

    def test_a_real_choice_is_kept_and_normalised(self, monkeypatch):
        from app.config import Settings

        monkeypatch.setenv("RT_DEFAULT_COUNTRY", "ma")
        assert Settings().default_country == "MA"

    def test_something_that_is_not_a_country_code_is_not_used(self, monkeypatch):
        from app.config import Settings

        monkeypatch.setenv("RT_DEFAULT_COUNTRY", "Egypt")
        assert Settings().default_country == "US"

    async def test_someone_with_no_country_still_gets_a_lookup(self, client, fake_idp, db_session):
        """The end of the chain: the fallback has to be usable, or the fix
        above only moves the silence one step along."""
        await do_login(client, fake_idp, LORDO)
        me = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
        me.country_code = None
        me.prefs = {}
        await db_session.commit()

        countries = _where_they_watch(me)
        assert countries, "never an empty list"
        assert all(len(c) == 2 for c in countries), countries
