"""Three things that were quietly wrong, and are cheap to keep right.

None of these are features. They are the difference between the app being
usable and the app being technically correct: a vector search with no index,
people with no address, and suggestions for services nobody pays for.
"""

from sqlalchemy import select, text

from app.ai import rails
from app.models import User
from app.social import handles
from tests.util import do_login


class TestTheVectorIndexExists:
    async def test_title_embeddings_has_an_ann_index(self, db_session):
        """Without it every shelf is an exact scan of the whole table and
        sorts the result, which is the real reason the home page needed a
        cache and a streaming response to feel bearable."""
        rows = (
            (
                await db_session.execute(
                    text("SELECT indexdef FROM pg_indexes WHERE tablename = 'title_embeddings'")
                )
            )
            .scalars()
            .all()
        )
        assert any("hnsw" in row.lower() for row in rows), rows
        # The operator class has to match the distance the query uses, or
        # the planner ignores the index and nothing looks wrong.
        assert any("vector_cosine_ops" in row for row in rows), rows

    async def test_the_model_column_is_indexed(self, db_session):
        """Every vector query filters on it first."""
        rows = (
            (
                await db_session.execute(
                    text("SELECT indexdef FROM pg_indexes WHERE tablename = 'title_embeddings'")
                )
            )
            .scalars()
            .all()
        )
        assert any("(model)" in row for row in rows), rows


class TestEveryoneGetsAnAddress:
    async def test_a_new_password_account_gets_a_handle(self, client, db_session):
        """A profile has no address other than its handle. Without one the
        person is not clickable anywhere and cannot be messaged, which was
        the default state of every account."""
        made = await client.post(
            "/api/auth/password/register",
            json={"username": "Newcomer", "password": "a-long-enough-password"},
        )
        assert made.status_code == 201, made.text

        user = (
            await db_session.execute(select(User).where(User.username == "Newcomer"))
        ).scalar_one()
        assert user.handle == "newcomer"

    async def test_a_new_sso_account_gets_a_handle(self, client, fake_idp, db_session):
        await do_login(client, fake_idp, {"sub": "h1", "preferred_username": "Arrival"})
        user = (
            await db_session.execute(select(User).where(User.username == "Arrival"))
        ).scalar_one()
        assert user.handle == "arrival"

    async def test_a_taken_handle_does_not_collide(self, client, fake_idp, db_session):
        await do_login(client, fake_idp, {"sub": "h2", "preferred_username": "Twin"})
        first = (await db_session.execute(select(User).where(User.username == "Twin"))).scalar_one()
        assert first.handle == "twin"

        second = User(
            tenant_id=first.tenant_id,
            username="twin-two",
            email="twin2@test",
            services=[],
            prefs={},
        )
        db_session.add(second)
        await db_session.flush()
        # Asking for the same stem is the collision that matters: usernames
        # are unique, but the handles derived from them need not be.
        assigned = await handles.assign(db_session, second, prefer="Twin")
        assert assigned == "twin_2"

    async def test_an_awkward_username_still_yields_something_legal(
        self, client, fake_idp, db_session
    ):
        """Handles are strict; the names people sign up with are not."""
        await do_login(client, fake_idp, {"sub": "h3", "preferred_username": "99 Red Balloons!"})
        user = (
            await db_session.execute(select(User).where(User.username == "99 Red Balloons!"))
        ).scalar_one()
        assert user.handle is not None
        assert handles.clean(user.handle) == user.handle, "must survive its own validator"

    async def test_someone_who_chose_a_handle_keeps_it(self, client, fake_idp, db_session):
        await do_login(client, fake_idp, {"sub": "h4", "preferred_username": "Chooser"})
        user = (
            await db_session.execute(select(User).where(User.username == "Chooser"))
        ).scalar_one()
        await handles.claim(db_session, user, "my_own_name")
        await db_session.commit()

        assert await handles.assign(db_session, user) == "my_own_name"


class TestOnlyWhatYouSubscribeTo:
    async def test_the_filter_is_on_by_default(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key
    ):
        """Showing someone a Netflix title when they do not have Netflix is
        an advert for somebody else's product."""
        await do_login(client, fake_idp, {"sub": "s1", "preferred_username": "subscriber"})
        user = (
            await db_session.execute(select(User).where(User.username == "subscriber"))
        ).scalar_one()
        user.services = [8]
        user.country_code = "US"
        await db_session.commit()

        got = await rails._service_filter(db_session, user)
        assert got is not None
        assert got.providers == [8]
        assert got.countries == ["US"]
        assert got.anywhere == [], "Netflix is listed in the US, so it is a normal filter"

    async def test_it_can_be_turned_off(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key
    ):
        await do_login(client, fake_idp, {"sub": "s2", "preferred_username": "everything"})
        user = (
            await db_session.execute(select(User).where(User.username == "everything"))
        ).scalar_one()
        user.services = [8]
        user.country_code = "US"
        user.prefs = {"only_my_services": False}
        await db_session.commit()

        assert await rails._service_filter(db_session, user) is None

    async def test_an_account_that_has_picked_nothing_is_not_filtered_to_nothing(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key
    ):
        """The default is only safe because of this: a new account has no
        services yet, and filtering on an empty set would empty every
        shelf."""
        await do_login(client, fake_idp, {"sub": "s3", "preferred_username": "fresh"})
        user = (await db_session.execute(select(User).where(User.username == "fresh"))).scalar_one()
        assert user.services == []
        assert await rails._service_filter(db_session, user) is None

        user.services = [8]
        await db_session.commit()
        assert await rails._service_filter(db_session, user) is None, "a country is needed too"
