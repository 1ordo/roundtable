"""Finding a title from a description of what happens in it.

Every case here was measured against a real 21,000 title catalog before the
code was written, and the numbers are in the docstrings. They are the reason
the implementation looks the way it does, so a change that breaks one of
these is a change that undoes a measurement.
"""

from sqlalchemy import select

from app.catalog import plotsearch
from app.models import Title


async def a_title(db, tmdb_id, name, overview, keywords, rating=7.5, votes=5000):
    title = Title(
        tmdb_id=tmdb_id,
        type="movie",
        name=name,
        overview=overview,
        keywords=keywords,
        tmdb_rating=rating,
        tmdb_votes=votes,
        popularity=20.0,
    )
    db.add(title)
    await db.flush()
    return title


async def seed(db):
    """Three real films with their real TMDB keywords, and one distractor
    that is more popular than all of them."""
    await a_title(
        db,
        137,
        "Groundhog Day",
        "A weatherman finds himself inexplicably living the same day over and over again.",
        ["deja vu", "time loop", "time warp", "small town"],
    )
    await a_title(
        db,
        27205,
        "Inception",
        "Cobb, a skilled thief who commits corporate espionage by infiltrating the "
        "subconscious of his targets, is offered a chance to regain his old life.",
        ["dream world", "subconscious", "dreams", "heist"],
    )
    await a_title(
        db,
        8916,
        "Honey, I Shrunk the Kids",
        "The scientist father of a teenage girl and boy accidentally shrinks his "
        "and two neighbouring teens to the size of insects.",
        ["shrinking", "miniaturization", "suburb", "invention"],
    )
    # Famous, well rated, nothing to do with any of the above. If the priors
    # ever outrank relevance, this is what comes back instead.
    await a_title(
        db,
        496243,
        "Parasite",
        "All unemployed, Ki-taek's family takes peculiar interest in the wealthy Parks.",
        ["class differences", "seoul", "con artist"],
        rating=8.5,
        votes=400000,
    )
    await db.commit()


class TestConceptSearch:
    async def test_the_time_loop_film_is_found_by_concept(self, db_session):
        """Measured: the lexical encoder put Groundhog Day at rank 13,614 of
        21,018 for a paraphrase of its own plot. The keywords find it."""
        await seed(db_session)
        found = await plotsearch.search(db_session, ["time loop", "deja vu"])
        assert found, "no match at all"
        assert found[0].name == "Groundhog Day"

    async def test_inception_is_found_although_its_overview_never_says_dream(self, db_session):
        """The case that decides the whole design. Inception's synopsis does
        not contain the word "dream"; only its keywords do. Any approach
        that searches the plot prose alone cannot find it."""
        await seed(db_session)
        inception = (
            await db_session.execute(select(Title).where(Title.name == "Inception"))
        ).scalar_one()
        assert "dream" not in (inception.overview or "").lower(), (
            "the premise of this test is that the overview does not say dream"
        )

        found = await plotsearch.search(db_session, ["dream world", "subconscious"])
        assert found and found[0].name == "Inception"

    async def test_relevance_outranks_fame(self, db_session):
        """Ranking by the quality and popularity priors alone answered a
        question about time loops with Parasite. Relevance leads; the priors
        may only break ties between equally relevant rows."""
        await seed(db_session)
        found = await plotsearch.search(db_session, ["time loop", "deja vu"])
        names = [t.name for t in found]
        assert names[0] == "Groundhog Day"
        assert "Parasite" not in names

    async def test_a_multi_word_concept_is_a_phrase_not_two_words(self, db_session):
        """ "time loop" must not match a title that says "time" somewhere and
        "loop" somewhere else."""
        await seed(db_session)
        assert plotsearch._tsquery(["time loop"], "|") == "(time <-> loop)"


class TestWithoutAModel:
    async def test_the_persons_own_words_still_find_it(self, db_session):
        """No chat model configured. Measured: this exact question returned
        Honey, I Shrunk the Kids at rank one from the words alone."""
        await seed(db_session)
        words = plotsearch.fallback_terms("the movie where a guy shrinks his kids")
        assert "shrinks" in words
        found = await plotsearch.search(db_session, words, require_all=True)
        assert found and found[0].name == "Honey, I Shrunk the Kids"

    async def test_framing_words_are_stripped(self, db_session):
        """Left in, the framing dominates a short query: "the one where they
        go into dreams" scored a disaster film above Inception."""
        words = plotsearch.fallback_terms("the one where they go into dreams")
        assert "dreams" in words
        for noise in ("the", "one", "where", "they", "into", "movie"):
            assert noise not in words

    async def test_and_not_or(self, db_session):
        """Measured: the OR variant of the shrinking question returned House
        Party. AND is what makes the no-model path usable."""
        await seed(db_session)
        words = ["shrinks", "kids"]
        anded = await plotsearch.search(db_session, words, require_all=True)
        assert [t.name for t in anded] == ["Honey, I Shrunk the Kids"]


class TestItDoesNotFireOnEverything:
    async def test_a_recommendation_request_is_not_a_recall_request(self):
        """The full-text leg costs a query, and "what should I watch" gains
        nothing from it."""
        from app.ai.chat import _sounds_like_recall

        assert _sounds_like_recall("what is the film where a guy relives the same day")
        assert _sounds_like_recall("the one where they go into dreams")
        assert _sounds_like_recall("I forgot the name of that space movie")
        assert not _sounds_like_recall("what should I watch tonight")
        assert not _sounds_like_recall("something like Coco but not animated")

    async def test_nonsense_does_not_raise(self, db_session):
        """A question that makes no query is a bad question, not a 500."""
        await seed(db_session)
        assert await plotsearch.search(db_session, []) == []
        assert await plotsearch.search(db_session, ["!!!", "&&&"]) == []
