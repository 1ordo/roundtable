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


class TestAServiceTheSourceHasNeverHeardOfHere:
    """ "My Disney is Egyptian."

    TMDB does not list Disney Plus as operating in Egypt. Not "this film is
    not on it" — the provider is absent from the region entirely, alongside
    Saudi Arabia and the UAE, where it lists OSN+ instead. Egypt is not a
    blank spot generally: eighteen thousand availability rows, Netflix with
    two and a half thousand. It is Disney Plus specifically that the source
    does not model there, with two rows across the whole catalog.

    So the app told somebody holding an Egyptian Disney Plus subscription
    that no Marvel film was on any service they had, and cut those films
    from their own recommendations, on the strength of a hole in a dataset.
    Absence of data is not evidence of absence, and the person who pays the
    subscription knows better than we do.
    """

    async def test_a_service_listed_in_your_country_is_filtered_normally(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key
    ):
        """Netflix in the United States is well covered, so a missing row
        there is a real answer and the country still applies."""
        from app.catalog import coverage

        assert await coverage.unlisted_services(db_session, ["US"], [8]) == set()

    async def test_a_service_the_region_does_not_list_is_unknown_not_absent(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key, monkeypatch
    ):
        from app.catalog import coverage, tmdb

        async def only_local(db, country):
            # What TMDB actually answers for Egypt: OSN+ and Shahid, no
            # Disney Plus anywhere in the list.
            return {
                "results": [
                    {"provider_id": 8, "provider_name": "Netflix"},
                    {"provider_id": 629, "provider_name": "OSN+"},
                ]
            }

        monkeypatch.setattr(tmdb, "provider_list", only_local)
        unlisted = await coverage.unlisted_services(db_session, ["EG"], [8, 337, 629])
        assert unlisted == {337}, "Disney Plus is unknown in Egypt; the other two are not"

    async def test_one_country_that_lists_it_is_enough(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key
    ):
        """Somebody with Egypt and Britain can be told honestly where
        Disney Plus does and does not carry something, so nothing is
        widened for them."""
        from app.catalog import coverage

        assert await coverage.unlisted_services(db_session, ["EG", "GB"], [337]) == set()

    async def test_a_source_outage_widens_nothing(self, client, fake_idp, db_session, monkeypatch):
        """A failed lookup must not be read as "no providers here", or every
        service anybody owns silently becomes unfiltered."""
        from app.catalog import coverage, tmdb

        async def broken(db, country):
            raise tmdb.TmdbError("upstream down")

        monkeypatch.setattr(tmdb, "provider_list", broken)
        assert await coverage.unlisted_services(db_session, ["EG"], [8, 337]) == set()

    async def test_an_empty_provider_list_is_a_broken_answer(
        self, client, fake_idp, db_session, monkeypatch
    ):
        """No country has zero services. Believing one does would mark every
        service the person owns as unknown."""
        from app.catalog import coverage, tmdb

        async def empty(db, country):
            return {"results": []}

        monkeypatch.setattr(tmdb, "provider_list", empty)
        assert await coverage.unlisted_services(db_session, ["EG"], [8, 337]) == set()

    async def test_the_shelf_filter_drops_the_country_for_such_a_service(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key, monkeypatch
    ):
        from app.ai import rails
        from app.catalog import tmdb

        async def no_disney(db, country):
            return {"results": [{"provider_id": 8, "provider_name": "Netflix"}]}

        monkeypatch.setattr(tmdb, "provider_list", no_disney)
        await do_login(client, fake_idp, LORDO)
        me = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
        me.country_code = "EG"
        me.services = [8, 337]
        me.prefs = {"only_my_services": True}
        await db_session.commit()

        got = await rails._service_filter(db_session, me)
        assert got is not None
        assert got.providers == [8], "Netflix is covered in Egypt, so it keeps the country"
        assert got.countries == ["EG"]
        assert got.anywhere == [337], "Disney Plus matches without a country"
        assert got.matches_anything

    async def test_the_title_page_shows_it_and_says_it_is_not_a_local_listing(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key, monkeypatch
    ):
        """The whole complaint, end to end."""
        from app.catalog import tmdb

        async def no_disney(db, country):
            return {"results": [{"provider_id": 8, "provider_name": "Netflix"}]}

        monkeypatch.setattr(tmdb, "provider_list", no_disney)
        await do_login(client, fake_idp, LORDO)
        me = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
        me.country_code = "EG"
        me.prefs = {}
        me.services = [337]
        await a_marvel_film(db_session)
        film = (await db_session.execute(select(Title).where(Title.tmdb_id == 1726))).scalar_one()
        db_session.add(
            Availability(
                title_id=film.id,
                country="US",
                provider_id=337,
                provider_name="Disney Plus",
                kind="stream",
            )
        )
        await db_session.commit()

        resp = await client.get("/api/titles/movie/1726")
        assert resp.status_code == 200, resp.text
        egypt = resp.json()["availability"]["EG"]
        disney = [p for p in egypt if p["provider_name"] == "Disney Plus"]
        assert disney, "they pay for it and it carries the film; do not tell them it is nowhere"
        assert disney[0]["unlisted_locally"] is True, "shown, but not claimed as a local listing"
        assert [p for p in egypt if p["provider_name"] == "Apple TV Store"], "real rows stay"

    async def test_a_service_they_do_not_pay_for_is_not_conjured_up(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key, monkeypatch
    ):
        """This leans on the person's own subscription. Without that claim
        there is nothing to prefer over the data."""
        from app.catalog import tmdb

        async def no_disney(db, country):
            return {"results": [{"provider_id": 8, "provider_name": "Netflix"}]}

        monkeypatch.setattr(tmdb, "provider_list", no_disney)
        await do_login(client, fake_idp, LORDO)
        me = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
        me.country_code = "EG"
        me.prefs = {}
        me.services = []
        await a_marvel_film(db_session)
        film = (await db_session.execute(select(Title).where(Title.tmdb_id == 1726))).scalar_one()
        db_session.add(
            Availability(
                title_id=film.id,
                country="US",
                provider_id=337,
                provider_name="Disney Plus",
                kind="stream",
            )
        )
        await db_session.commit()

        resp = await client.get("/api/titles/movie/1726")
        egypt = resp.json()["availability"]["EG"]
        assert not [p for p in egypt if p["provider_name"] == "Disney Plus"]
