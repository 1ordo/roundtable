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

        # The fallback is now the agent, so give it a scripted final answer.
        import json

        from app.ai import agent
        from app.ai import client as ai_client

        async def scripted(db, messages, tools, max_tokens=1200):
            return {
                "content": json.dumps(
                    {"reply": "I could not resolve that set.", "titles": [], "list_name": None}
                )
            }

        monkeypatch.setattr(ai_client, "chat_tools", scripted)
        monkeypatch.setattr(agent.client, "chat_tools", scripted)

        keys = []
        async for step in chat.answer_steps(db_session, user, "marvel movies in order"):
            if step.get("type") == "step":
                keys.append(step["key"])
        assert "resolve-miss" in keys, "it should say it could not, then carry on"


class TestNamingAFranchiseIsEnough:
    """Asked "where and where to watch harry potter?", the assistant answered
    with The Flash.

    The franchise path existed and was correct, but it only fired on a
    phrase like "in order" or "all the". A plain "where can I watch X" fell
    through to the embedding shortlist, which for that question ranked
    KanColle, Gundam 00, Attack on Titan and Panty & Stocking above Harry
    Potter, and put Fantastic Beasts and Where to Find Them above it too,
    because the encoder matched the word "where" out of the framing rather
    than the subject of the sentence.

    A question that names a franchise is about that franchise however it is
    phrased, so recognition no longer waits to be told twice.
    """

    def test_the_question_that_answered_the_flash(self):
        assert chat._franchise_intent("where and where to watch harry potter?") == "harry potter"

    def test_any_way_of_asking_where(self):
        for question in (
            "where to watch harry potter",
            "how can i watch harry potter",
            "where is harry potter streaming",
            "harry potter",
            "what platform has harry potter",
        ):
            assert chat._franchise_intent(question) == "harry potter", question

    def test_a_franchise_named_as_a_comparison_is_still_not_one(self):
        """The reason the gate existed. Something like Harry Potter wants a
        film that resembles it, not the eight that are it."""
        for question in (
            "something like harry potter",
            "a film similar to harry potter",
            "recommend me something like the marvel films",
            "anything that reminds me of harry potter",
        ):
            assert chat._franchise_intent(question) is None, question

    def test_a_franchise_named_as_a_qualifier_on_one_pick_is_not_one(self):
        for question in (
            "a marvel film for tonight",
            "is the new marvel any good",
            "is harry potter worth watching",
        ):
            assert chat._franchise_intent(question) is None, question

    def test_a_question_naming_nothing_survives_the_strip_as_nothing(self):
        """Generic words are never a franchise name. Without dropping them,
        "something good" reaches the collection search, which obliges."""
        for question in (
            "what should i watch tonight",
            "something good",
            "anything good",
            "recommend me a comedy",
            "i want something new",
        ):
            assert chat._franchise_intent(question) is None, question

    def test_a_sentence_the_strip_could_not_reduce_is_not_a_name(self):
        """A franchise name is short. A long tail of leftover words means
        the strip never found one."""
        assert chat._franchise_intent("has anyone seen my keys around the house lately") is None


class TestAnsweringTheWhere:
    """ "Where can I watch Harry Potter" is a question about services.

    Answering it with eight posters and a sentence about release order is
    answering a different question. The availability is already in the
    table next to the titles.
    """

    async def test_it_names_the_services_and_how_much_each_one_has(
        self, client, fake_idp, db_session
    ):
        from sqlalchemy import select

        from app.ai import chat
        from app.models import Availability, Title, User
        from tests.util import LORDO, do_login

        await do_login(client, fake_idp, LORDO)
        me = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
        me.country_code = "EG"

        films = []
        for n in range(3):
            film = Title(tmdb_id=940_000 + n, type="movie", name=f"Potter {n}")
            db_session.add(film)
            films.append(film)
        await db_session.flush()
        for film in films:
            db_session.add(
                Availability(
                    title_id=film.id,
                    country="EG",
                    provider_id=8,
                    provider_name="Netflix",
                    kind="stream",
                )
            )
        # One of the three, so the count has to distinguish it from Netflix.
        db_session.add(
            Availability(
                title_id=films[0].id,
                country="EG",
                provider_id=384,
                provider_name="HBO Max",
                kind="stream",
            )
        )
        await db_session.commit()

        said = await chat._where_to_watch(db_session, me, films)
        assert "Netflix has all of them" in said, said
        assert "HBO Max has 1 of them" in said, said

    async def test_a_rental_is_not_streaming_it(self, client, fake_idp, db_session):
        """Someone asking where to watch a franchise is asking what carries
        it, not what will sell it to them one film at a time."""
        from sqlalchemy import select

        from app.ai import chat
        from app.models import Availability, Title, User
        from tests.util import LORDO, do_login

        await do_login(client, fake_idp, LORDO)
        me = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
        me.country_code = "EG"
        film = Title(tmdb_id=941_000, type="movie", name="Rented Only")
        db_session.add(film)
        await db_session.flush()
        db_session.add(
            Availability(
                title_id=film.id,
                country="EG",
                provider_id=2,
                provider_name="Apple TV",
                kind="rent",
            )
        )
        await db_session.commit()

        said = await chat._where_to_watch(db_session, me, [film])
        assert "Apple TV" not in said
        assert "None of them are streaming" in said

    def test_only_a_question_about_where_triggers_it(self):
        assert chat._ASKS_WHERE.search("where can i watch harry potter")
        assert chat._ASKS_WHERE.search("is harry potter streaming")
        assert chat._ASKS_WHERE.search("what service has harry potter")
        assert not chat._ASKS_WHERE.search("harry potter in order")
