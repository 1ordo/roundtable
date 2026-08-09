"""Ranking quality: taste leads, quality and popularity break ties, and the
cost per request stays flat as signals pile up."""

import numpy as np
from sqlalchemy import select

from app.ai import taste
from app.models import Title, TitleEmbedding, User
from tests.util import LORDO, do_login


class FakeTitle:
    def __init__(self, rating=None, votes=0, popularity=0.0, year=None, imdb=None):
        self.tmdb_rating = rating
        self.imdb_rating = imdb
        self.tmdb_votes = votes
        self.popularity = popularity
        self.year = year


def test_thin_ratings_are_shrunk_toward_the_mean():
    """A 9.6 from 40 votes must not outrank an 8.4 from 400,000."""
    obscure = taste.quality_prior(FakeTitle(rating=9.6, votes=40))
    proven = taste.quality_prior(FakeTitle(rating=8.4, votes=400_000))
    assert proven > obscure

    unknown = taste.quality_prior(FakeTitle())
    assert unknown == 0.5, "no rating is neutral, not zero"


def test_quality_prior_stays_in_range():
    for rating, votes in ((10.0, 10_000_000), (0.5, 1), (None, 0)):
        value = taste.quality_prior(FakeTitle(rating=rating, votes=votes))
        assert 0.0 <= value <= 1.0


def test_popularity_is_log_scaled():
    small = taste.popularity_prior(FakeTitle(popularity=2.0))
    large = taste.popularity_prior(FakeTitle(popularity=60.0))
    huge = taste.popularity_prior(FakeTitle(popularity=6000.0))
    assert small < large < huge
    assert huge <= 1.0, "a runaway hit cannot dominate everything"
    assert taste.popularity_prior(FakeTitle(popularity=0.0)) == 0.0
    # Doubling popularity is a smaller step the higher you already are.
    assert (large - small) > (huge - large)


def test_recency_favours_newer_without_burying_classics():
    new = taste.recency_prior(FakeTitle(year=2025), 2026)
    old = taste.recency_prior(FakeTitle(year=1975), 2026)
    assert new > old
    assert old > 0.1, "a classic is still a candidate"
    assert taste.recency_prior(FakeTitle(), 2026) == 0.5


async def test_quality_breaks_ties_between_equally_close_titles(
    db_session, ai_enabled, fake_tmdb_http
):
    """Two titles the same distance from the taste vector: the better made
    one goes first."""
    from app.ai.client import get_ai_settings

    settings = await get_ai_settings(db_session)
    vector = np.zeros(768)
    vector[0] = 1.0

    for name, rating, votes, popularity in (
        ("Thin Praise", 9.7, 30, 1.0),
        ("Widely Loved", 8.3, 500_000, 90.0),
    ):
        title = Title(
            tmdb_id=abs(hash(name)) % 100000,
            type="movie",
            name=name,
            genres=[{"id": 18, "name": "Drama"}],
            poster_path="/p.jpg",
            tmdb_rating=rating,
            tmdb_votes=votes,
            popularity=popularity,
            year=2020,
        )
        db_session.add(title)
        await db_session.flush()
        db_session.add(
            TitleEmbedding(title_id=title.id, model=settings.embed_model, embedding=vector.tolist())
        )
    await db_session.commit()

    ranked = await taste.diversified_ranking(db_session, vector, limit=2)
    names = [t.name for t, _ in ranked]
    assert names[0] == "Widely Loved", "identical similarity, so quality decides"


async def test_taste_is_not_rebuilt_on_every_read(
    client, fake_idp, fake_tmdb_http, db_session, ai_enabled, monkeypatch
):
    """Rebuilding reads every signal, so it must not happen per request."""
    await do_login(client, fake_idp, LORDO)
    headers = {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}
    await client.get("/api/titles/movie/354912")
    await client.post("/api/history", json={"type": "movie", "tmdb_id": 354912}, headers=headers)

    user = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
    first = await taste.get_taste(db_session, user)
    await db_session.commit()
    assert first is not None

    rebuilds = {"n": 0}
    original = taste.compute_taste

    async def counting(db, person):
        rebuilds["n"] += 1
        return await original(db, person)

    monkeypatch.setattr(taste, "compute_taste", counting)

    for _ in range(5):
        await taste.get_taste(db_session, user)
    await db_session.commit()
    assert rebuilds["n"] == 0, "the cached vector is reused"


async def test_a_verdict_rebuilds_at_once(client, fake_idp, fake_tmdb_http, db_session, ai_enabled):
    """A like should change what you are shown immediately."""
    from app.models import UserTaste

    await do_login(client, fake_idp, LORDO)
    headers = {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}
    await client.get("/api/titles/movie/354912")
    await client.get("/api/titles/tv/456")
    await client.post("/api/history", json={"type": "movie", "tmdb_id": 354912}, headers=headers)

    user = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
    await taste.get_taste(db_session, user)
    await db_session.commit()

    await client.post("/api/titles/tv/456/signal", json={"kind": "like"}, headers=headers)

    cached = (
        await db_session.execute(select(UserTaste).where(UserTaste.user_id == user.id))
    ).scalar_one()
    await db_session.refresh(cached)
    assert cached.events_count == -1, "marked for rebuild rather than left stale"


def test_ranking_weights_keep_taste_in_charge():
    """The priors may break ties, never overturn a clear preference."""
    total_prior = taste.QUALITY_WEIGHT + taste.POPULARITY_WEIGHT + taste.RECENCY_WEIGHT
    assert total_prior < 0.25, "similarity ranges far wider than this"
    assert total_prior < taste.DIVERSITY_PENALTY, "variety still outweighs the priors"
