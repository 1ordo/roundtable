"""Per-panel privacy, everywhere a written thing can appear.

The profile page was never the problem. These endpoints are: a post reaches
the feed and the comments under a title, a quote reaches the title page, and
a reshare carries someone else's post inside it to an audience that was never
theirs. Each test below is a leak that shipped, so none of them should be
weakened without a very good reason.
"""

from sqlalchemy import select

from app.models import Friendship, Quote, Title, User
from app.social import visibility
from tests.util import do_login


async def csrf(client) -> dict:
    return {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}


async def make(db, username: str, level: str = "friends", panels: dict | None = None) -> User:
    from app.models import Tenant

    tenant = (await db.execute(select(Tenant))).scalars().first()
    user = User(
        tenant_id=tenant.id,
        username=username,
        email=f"{username}@test",
        visibility=level,
        prefs={"panel_visibility": panels} if panels else {},
    )
    db.add(user)
    await db.flush()
    return user


async def befriend(db, a: User, b: User) -> None:
    db.add(Friendship(requester_id=a.id, addressee_id=b.id, status="accepted"))
    await db.flush()


async def a_title(db) -> Title:
    found = (await db.execute(select(Title))).scalars().first()
    if found is not None:
        return found
    title = Title(tmdb_id=999001, type="movie", name="A Film")
    db.add(title)
    await db.flush()
    return title


class TestPanelSet:
    async def test_a_private_posts_panel_beats_a_public_account(self, client, fake_idp, db_session):
        """The leak that shipped: public account, posts set to private, and
        every post still turned up in everyone's feed."""
        await do_login(client, fake_idp, {"sub": "p1", "preferred_username": "viewer1"})
        viewer = (
            await db_session.execute(select(User).where(User.username == "viewer1"))
        ).scalar_one()
        loud = await make(db_session, "loud", "public", {"posts": "private"})
        await db_session.commit()

        # The account-level set still contains them, which is correct: their
        # numbers and favourites are public. Their posts are not.
        assert loud.id in await visibility.visible_user_ids(db_session, viewer)
        allowed = await visibility.visible_user_ids_for_panel(db_session, viewer, "posts")
        assert loud.id not in allowed

    async def test_a_public_panel_is_not_capped_by_a_friends_account(
        self, client, fake_idp, db_session
    ):
        """A panel level is the decision, not a further restriction on the
        account level, or nobody could open one panel without opening all."""
        await do_login(client, fake_idp, {"sub": "p2", "preferred_username": "viewer2"})
        viewer = (
            await db_session.execute(select(User).where(User.username == "viewer2"))
        ).scalar_one()
        shy = await make(db_session, "shy", "friends", {"posts": "public"})
        await db_session.commit()

        assert shy.id not in await visibility.visible_user_ids(db_session, viewer)
        allowed = await visibility.visible_user_ids_for_panel(db_session, viewer, "posts")
        assert shy.id in allowed

    async def test_a_panel_with_no_setting_falls_back_to_the_account(
        self, client, fake_idp, db_session
    ):
        await do_login(client, fake_idp, {"sub": "p3", "preferred_username": "viewer3"})
        viewer = (
            await db_session.execute(select(User).where(User.username == "viewer3"))
        ).scalar_one()
        opener = await make(db_session, "opener", "public")
        hermit = await make(db_session, "hermit2", "private")
        await befriend(db_session, viewer, hermit)
        await db_session.commit()

        allowed = await visibility.visible_user_ids_for_panel(db_session, viewer, "posts")
        assert opener.id in allowed
        assert hermit.id not in allowed

    async def test_you_always_see_your_own_panel(self, client, fake_idp, db_session):
        await do_login(client, fake_idp, {"sub": "p4", "preferred_username": "solo2"})
        solo = (await db_session.execute(select(User).where(User.username == "solo2"))).scalar_one()
        solo.prefs = {"panel_visibility": {"posts": "private"}}
        await db_session.commit()

        allowed = await visibility.visible_user_ids_for_panel(db_session, solo, "posts")
        assert solo.id in allowed


class TestFeedRespectsThePanel:
    async def test_the_feed_leaves_out_a_private_posts_panel(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key
    ):
        await do_login(client, fake_idp, {"sub": "f1", "preferred_username": "author1"})
        author = (
            await db_session.execute(select(User).where(User.username == "author1"))
        ).scalar_one()
        headers = await csrf(client)
        written = await client.post(
            "/api/posts",
            json={"body": "Something I would rather keep to myself."},
            headers=headers,
        )
        assert written.status_code == 201

        # Public account, but the posts panel is shut.
        author.visibility = "public"
        author.prefs = {"panel_visibility": {"posts": "private"}}
        await db_session.commit()

        await do_login(client, fake_idp, {"sub": "f2", "preferred_username": "reader1"})
        feed = await client.get("/api/feed")
        assert feed.status_code == 200
        bodies = [c["body"] for c in feed.json()["comments"]]
        assert "Something I would rather keep to myself." not in bodies


class TestResharesDoNotLeakTheOriginal:
    async def test_a_reshare_drops_an_original_the_reader_cannot_see(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key
    ):
        """A is friends with B and with C. C is not friends with B. A
        reshares B's friends-only post. C must not receive B's words."""
        await do_login(client, fake_idp, {"sub": "r_b", "preferred_username": "bee"})
        bee = (await db_session.execute(select(User).where(User.username == "bee"))).scalar_one()
        headers = await csrf(client)
        original = await client.post(
            "/api/posts",
            json={"body": "Between friends only, this one."},
            headers=headers,
        )
        assert original.status_code == 201
        original_id = original.json()["id"]

        await do_login(client, fake_idp, {"sub": "r_a", "preferred_username": "ay"})
        ay = (await db_session.execute(select(User).where(User.username == "ay"))).scalar_one()
        await befriend(db_session, ay, bee)
        await db_session.commit()

        headers = await csrf(client)
        shared = await client.post(
            "/api/posts",
            json={"body": "Everyone should read this.", "shares": original_id},
            headers=headers,
        )
        assert shared.status_code == 201, shared.text

        await do_login(client, fake_idp, {"sub": "r_c", "preferred_username": "cee"})
        cee = (await db_session.execute(select(User).where(User.username == "cee"))).scalar_one()
        await befriend(db_session, cee, ay)
        await db_session.commit()

        feed = await client.get("/api/feed")
        assert feed.status_code == 200
        posts = feed.json()["comments"]
        reshare = next(p for p in posts if p["body"] == "Everyone should read this.")
        # The resharer's own words survive; the original does not.
        assert reshare["shared"] is None
        assert "Between friends only, this one." not in feed.text

    async def test_a_reshare_keeps_the_original_when_the_reader_may_see_it(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key
    ):
        """The other half: dropping it always would be its own bug."""
        await do_login(client, fake_idp, {"sub": "r2_b", "preferred_username": "openbee"})
        openbee = (
            await db_session.execute(select(User).where(User.username == "openbee"))
        ).scalar_one()
        openbee.visibility = "public"
        await db_session.commit()
        headers = await csrf(client)
        original = await client.post(
            "/api/posts", json={"body": "Anyone may read this."}, headers=headers
        )
        original_id = original.json()["id"]

        await do_login(client, fake_idp, {"sub": "r2_a", "preferred_username": "sharer"})
        sharer = (
            await db_session.execute(select(User).where(User.username == "sharer"))
        ).scalar_one()
        sharer.visibility = "public"
        await db_session.commit()
        headers = await csrf(client)
        shared = await client.post(
            "/api/posts",
            json={"body": "Worth a look.", "shares": original_id},
            headers=headers,
        )
        assert shared.status_code == 201
        assert shared.json()["shared"] is not None
        assert shared.json()["shared"]["body"] == "Anyone may read this."


class TestQuotesRespectThePanel:
    async def test_a_private_users_quote_is_not_shown_on_the_title_page(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key
    ):
        """Quotes carry a name, so they are written things and belong to the
        posts panel. This endpoint filtered nothing at all."""
        await do_login(client, fake_idp, {"sub": "q1", "preferred_username": "quoter"})
        quoter = (
            await db_session.execute(select(User).where(User.username == "quoter"))
        ).scalar_one()
        title = await a_title(db_session)
        db_session.add(
            Quote(
                user_id=quoter.id,
                title_id=title.id,
                body="A line I liked.",
                character="Someone",
            )
        )
        quoter.visibility = "private"
        await db_session.commit()

        await do_login(client, fake_idp, {"sub": "q2", "preferred_username": "passerby"})
        page = await client.get(f"/api/titles/{title.type}/{title.tmdb_id}/quotes")
        assert page.status_code == 200
        assert "A line I liked." not in page.text

    async def test_your_own_quote_is_still_yours_to_see(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key
    ):
        await do_login(client, fake_idp, {"sub": "q3", "preferred_username": "keeper"})
        keeper = (
            await db_session.execute(select(User).where(User.username == "keeper"))
        ).scalar_one()
        title = await a_title(db_session)
        db_session.add(
            Quote(
                user_id=keeper.id,
                title_id=title.id,
                body="Mine to keep.",
                character="Someone",
            )
        )
        keeper.visibility = "private"
        await db_session.commit()

        page = await client.get(f"/api/titles/{title.type}/{title.tmdb_id}/quotes")
        assert page.status_code == 200
        assert "Mine to keep." in page.text


class TestChatPromptIsScopedToTheAsker:
    async def test_saved_titles_do_not_cross_between_users(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key
    ):
        """The saved-lists block in the assistant prompt had no owner
        predicate, so it read the first rows in the whole install."""
        from app.ai.chat import _profile_block
        from app.models import List as ListModel
        from app.models import ListItem

        await do_login(client, fake_idp, {"sub": "ch1", "preferred_username": "asker"})
        asker = (
            await db_session.execute(select(User).where(User.username == "asker"))
        ).scalar_one()
        other = await make(db_session, "otherperson")
        title = await a_title(db_session)

        secret = Title(tmdb_id=999002, type="movie", name="Not Your Business")
        db_session.add(secret)
        await db_session.flush()

        theirs = ListModel(
            tenant_id=other.tenant_id, user_id=other.id, name="Theirs", kind="watchlist"
        )
        db_session.add(theirs)
        await db_session.flush()
        db_session.add(ListItem(list_id=theirs.id, title_id=secret.id))

        mine = ListModel(tenant_id=asker.tenant_id, user_id=asker.id, name="Mine", kind="watchlist")
        db_session.add(mine)
        await db_session.flush()
        db_session.add(ListItem(list_id=mine.id, title_id=title.id))
        await db_session.commit()

        block = await _profile_block(db_session, asker)
        assert "Not Your Business" not in block
