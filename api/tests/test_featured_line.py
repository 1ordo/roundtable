"""One line above your name, instead of a shelf of every line you saved.

A list of saved lines is an inventory. The one somebody chose to put at the
top of their profile is a statement about them, and that is the thing worth
having.
"""

from sqlalchemy import select

from app.models import Quote, Title, User
from tests.util import LORDO, do_login


async def csrf(client) -> dict:
    return {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}


async def a_line(db, user_id=None, body="I am your father.") -> Quote:
    title = (await db.execute(select(Title))).scalars().first()
    if title is None:
        title = Title(
            tmdb_id=999801,
            type="movie",
            name="A Film",
            backdrop_path="/backdrop.jpg",
            poster_path="/poster.jpg",
            year=1980,
        )
        db.add(title)
        await db.flush()
    quote = Quote(title_id=title.id, user_id=user_id, body=body, character="Someone")
    db.add(quote)
    await db.flush()
    return quote


class TestFeaturing:
    async def test_featuring_a_line_puts_it_on_the_profile(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key
    ):
        await do_login(client, fake_idp, LORDO)
        me = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
        quote = await a_line(db_session, me.id)
        await db_session.commit()

        resp = await client.post(f"/api/quotes/{quote.id}/feature", headers=await csrf(client))
        assert resp.status_code == 200
        assert resp.json()["featured_quote_id"] == str(quote.id)

        profile = await client.get(f"/api/profiles/{me.handle}")
        line = profile.json()["featured_line"]
        assert line is not None
        assert line["body"] == "I am your father."
        # The cover is page width, so it needs the backdrop rather than the
        # poster. Both are sent; the poster is only a fallback.
        assert line["title"]["backdrop_path"] == "/backdrop.jpg"

    async def test_pressing_the_featured_one_again_clears_it(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key
    ):
        """The same control does both, so there is no separate remove."""
        await do_login(client, fake_idp, LORDO)
        me = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
        quote = await a_line(db_session, me.id)
        await db_session.commit()

        headers = await csrf(client)
        await client.post(f"/api/quotes/{quote.id}/feature", headers=headers)
        again = await client.post(f"/api/quotes/{quote.id}/feature", headers=headers)
        assert again.json()["featured_quote_id"] is None

        profile = await client.get(f"/api/profiles/{me.handle}")
        assert profile.json()["featured_line"] is None

    async def test_only_one_is_featured_at_a_time(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key
    ):
        """One each is the schema saying so, not a rule the code remembers."""
        await do_login(client, fake_idp, LORDO)
        me = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
        first = await a_line(db_session, me.id, "The first one.")
        second = await a_line(db_session, me.id, "The second one.")
        await db_session.commit()

        headers = await csrf(client)
        await client.post(f"/api/quotes/{first.id}/feature", headers=headers)
        await client.post(f"/api/quotes/{second.id}/feature", headers=headers)

        profile = await client.get(f"/api/profiles/{me.handle}")
        assert profile.json()["featured_line"]["body"] == "The second one."

    async def test_a_catalog_line_can_be_featured(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key
    ):
        """Quoting somebody else's favourite line is the normal way a line
        gets used, and the film is credited either way."""
        await do_login(client, fake_idp, LORDO)
        quote = await a_line(db_session, None, "Nobody wrote this one down.")
        await db_session.commit()

        resp = await client.post(f"/api/quotes/{quote.id}/feature", headers=await csrf(client))
        assert resp.status_code == 200

    async def test_deleting_the_line_clears_the_feature_rather_than_the_account(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key
    ):
        """SET NULL, not cascade. Removing a quote must not remove a person."""
        await do_login(client, fake_idp, LORDO)
        me = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
        quote = await a_line(db_session, me.id)
        await db_session.commit()
        await client.post(f"/api/quotes/{quote.id}/feature", headers=await csrf(client))

        await client.delete(f"/api/quotes/{quote.id}", headers=await csrf(client))

        still_here = (
            await db_session.execute(select(User).where(User.username == "Lordo"))
        ).scalar_one_or_none()
        assert still_here is not None, "deleting a quote must not delete the person"
        await db_session.refresh(still_here)
        assert still_here.featured_quote_id is None

    async def test_it_is_reported_on_me_so_the_button_knows_its_state(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key
    ):
        await do_login(client, fake_idp, LORDO)
        me = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
        quote = await a_line(db_session, me.id)
        await db_session.commit()

        assert (await client.get("/api/me")).json()["user"]["featured_quote_id"] is None
        await client.post(f"/api/quotes/{quote.id}/feature", headers=await csrf(client))
        assert (await client.get("/api/me")).json()["user"]["featured_quote_id"] == str(quote.id)


class TestPrivacy:
    async def test_a_private_profile_does_not_show_its_line(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key
    ):
        """The cover is part of the profile, so it obeys the same panel as
        everything else somebody wrote."""
        await do_login(client, fake_idp, LORDO)
        me = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
        quote = await a_line(db_session, me.id)
        await db_session.commit()
        await client.post(f"/api/quotes/{quote.id}/feature", headers=await csrf(client))

        me.prefs = {"panel_visibility": {"posts": "private"}}
        me.visibility = "public"
        handle = me.handle
        await db_session.commit()

        await do_login(client, fake_idp, {"sub": "fl-x", "preferred_username": "stranger_fl"})
        profile = await client.get(f"/api/profiles/{handle}")
        assert profile.status_code == 200
        assert profile.json()["featured_line"] is None
