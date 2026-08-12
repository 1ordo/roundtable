"""Asking the assistant for a franchise.

Written against a real failure. Asked "I wanna watch marvel movies, make me
a list ordered so i can start watching", the assistant searched the catalog
by embedding similarity, considered Where's Waldo, The Mexican and Lord of
the Rings, and recommended a DC film. The default encoder compares the words
two texts share, and "marvel movies" shares none with anything useful.

The answer is not a better shortlist. It is not asking the model at all: the
catalog knows which films are in a franchise and when they came out.
"""

from app.ai import chat


class TestRecognisingTheAsk:
    def test_asking_for_the_set_is_a_franchise_question(self):
        for question in (
            "I wanna watch marvel movies, make me a list ordered so i can start watching",
            "marvel movies in order",
            "show me all the marvel films",
            "where do i start with the mcu",
            "harry potter in order",
        ):
            assert chat._franchise_intent(question) is not None, question

    def test_merely_mentioning_one_is_not(self):
        """Someone asking for one film like a Marvel film wants a
        recommendation, not thirty-nine of them."""
        for question in (
            "something like a marvel film but funnier",
            "is the new marvel any good",
            "a marvel film for tonight",
        ):
            assert chat._franchise_intent(question) is None, question

    def test_a_franchise_outside_the_registry_is_still_recognised(self):
        """Fast and Furious is a TMDB collection rather than a registry
        entry, so the intent check hands the leftover words to the resolver
        and lets it decide. The registry is only for franchises too big to
        be a collection."""
        assert chat._franchise_intent("all the fast and furious films") == "fast furious"

    def test_a_question_naming_no_franchise_is_not_one(self):
        assert chat._franchise_intent("what should i watch tonight") is None
        assert chat._franchise_intent("something good") is None

    def test_the_framing_is_stripped_before_looking_anything_up(self):
        """A collection lookup on a whole sentence matches nothing."""
        assert chat._franchise_query("harry potter in order") == "harry potter"
        assert "wanna" not in chat._franchise_query("i wanna watch harry potter in order")


class TestTheTraceDescribesWhatHappened:
    async def test_a_franchise_question_is_narrated_as_one(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key, ai_enabled, monkeypatch
    ):
        """The trace said "searching the catalog, 40 closest of 22403" for a
        question that never searched the catalog. A trace that reports work
        which did not happen is decoration."""
        from sqlalchemy import select

        from app.catalog import watch_order
        from app.models import User
        from tests.util import LORDO, do_login

        await do_login(client, fake_idp, LORDO)
        user = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()

        async def fake_resolve(db, query=None, tmdb_id=None, media_type="movie", user=None):
            return watch_order.WatchOrder(
                name="Marvel Cinematic Universe",
                kind="universe",
                titles=[
                    watch_order.OrderedTitle(
                        354912, "movie", "Coco", 2017, None, None, None, watched=False
                    )
                ],
                note="",
            )

        monkeypatch.setattr(watch_order, "resolve", fake_resolve)

        keys = []
        done = None
        async for step in chat.answer_steps(db_session, user, "marvel movies in order"):
            if step.get("type") == "step":
                keys.append(step["key"])
            if step.get("type") == "done":
                done = step

        assert "resolve" in keys, f"never said it resolved a franchise: {keys}"
        assert "order" in keys, f"never said it ordered them: {keys}"
        assert "ask" not in keys, "it should not claim to have asked the model"
        assert "search" not in keys, "it should not claim to have searched the shortlist"
        assert done is not None

    async def test_a_franchise_answer_offers_the_whole_thing_as_a_list(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key, ai_enabled, monkeypatch
    ):
        """The point of the feature: one press to keep it."""
        from sqlalchemy import select

        from app.catalog import watch_order
        from app.models import User
        from tests.util import LORDO, do_login

        await do_login(client, fake_idp, LORDO)
        user = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()

        async def fake_resolve(db, query=None, tmdb_id=None, media_type="movie", user=None):
            return watch_order.WatchOrder(
                name="Marvel Cinematic Universe",
                kind="universe",
                titles=[
                    watch_order.OrderedTitle(
                        354912, "movie", "Coco", 2017, None, None, None, watched=False
                    ),
                    watch_order.OrderedTitle(
                        456, "tv", "Example Show", 2019, None, None, None, watched=False
                    ),
                ],
                note="",
            )

        monkeypatch.setattr(watch_order, "resolve", fake_resolve)

        out = await chat.answer(db_session, user, "marvel movies in order")
        assert out["proposal"] is not None, "a franchise answer should offer the list"
        assert out["proposal"]["name"] == "Marvel Cinematic Universe"
        # The proposal carries the whole franchise, not only what happened to
        # be in the catalog already.
        assert len(out["proposal"]["titles"]) == 2
        assert "release order" in out["reply"]

    async def test_an_unresolvable_franchise_falls_back_rather_than_failing(
        self, client, fake_idp, db_session, fake_tmdb_http, tmdb_key, ai_enabled, monkeypatch
    ):
        from sqlalchemy import select

        from app.catalog import watch_order
        from app.models import User
        from tests.util import LORDO, do_login

        await do_login(client, fake_idp, LORDO)
        user = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()

        async def nothing(db, query=None, tmdb_id=None, media_type="movie", user=None):
            return None

        monkeypatch.setattr(watch_order, "resolve", nothing)

        keys = []
        async for step in chat.answer_steps(db_session, user, "marvel movies in order"):
            if step.get("type") == "step":
                keys.append(step["key"])
        assert "resolve-miss" in keys, "it should say it could not, then carry on"
