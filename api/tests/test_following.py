"""Following actors: the follow itself, search, alerts, and ranking."""

from app.ai import taste
from app.models import FollowedPerson, Title, User
from tests.util import do_login


async def sign_in(client, fake_idp, name: str) -> str:
    await do_login(client, fake_idp, {"sub": f"sub-{name}", "preferred_username": name})
    return (await client.get("/api/me")).json()["csrf"]


async def test_only_top_billing_and_directors_count_as_followed(db_session):
    """A followed actor twentieth on the call sheet is not why anyone picks
    a film, so deep credits must not trigger the boost.

    Asked of Postgres rather than of a Python helper, because that is where
    the question is answered: shipping raw_tmdb back for a whole candidate
    pool costs more than the boost is worth."""
    cases = {
        "starring": {"cast": [{"id": 500, "name": "Them"}], "crew": []},
        # Sixteen names deep. Present, but not why anyone would pick it.
        "cameo": {"cast": [{"id": i} for i in range(100, 115)] + [{"id": 500}], "crew": []},
        "directed": {"cast": [], "crew": [{"id": 500, "job": "Director"}]},
        # A different job by the same person is not the same claim.
        "catering": {"cast": [], "crew": [{"id": 500, "job": "Caterer"}]},
    }
    titles = {
        name: Title(tmdb_id=i, type="movie", name=name, genres=[], raw_tmdb={"credits": credits})
        for i, (name, credits) in enumerate(cases.items(), start=1)
    }
    for title in titles.values():
        db_session.add(title)
    await db_session.flush()

    hit = await taste.followed_title_ids(db_session, [t.id for t in titles.values()], {500})
    assert titles["starring"].id in hit
    assert titles["directed"].id in hit
    assert titles["cameo"].id not in hit
    assert titles["catering"].id not in hit

    # Nobody followed: no query, no boost, no error.
    assert (
        await taste.followed_title_ids(db_session, [t.id for t in titles.values()], set()) == set()
    )


async def test_a_title_with_odd_credits_does_not_crash_the_boost(db_session):
    """Titles ingested before credits were fetched, or from a provider having
    a bad day, must not take the whole shelf down with them."""
    odd = [
        Title(tmdb_id=101, type="movie", name="Bare", genres=[]),  # raw_tmdb null
        Title(tmdb_id=102, type="movie", name="Empty", genres=[], raw_tmdb={}),
        Title(tmdb_id=103, type="movie", name="NullCredits", genres=[], raw_tmdb={"credits": None}),
        # credits present but the wrong shape: jsonb_array_elements raises on
        # anything that is not an array, so the guards have to hold.
        Title(tmdb_id=104, type="movie", name="Scalar", genres=[], raw_tmdb={"credits": 7}),
        Title(
            tmdb_id=105,
            type="movie",
            name="StringCast",
            genres=[],
            raw_tmdb={"credits": {"cast": "nope", "crew": "nope"}},
        ),
        # A non-numeric id must not blow up the cast to int.
        Title(
            tmdb_id=106,
            type="movie",
            name="OddId",
            genres=[],
            raw_tmdb={"credits": {"cast": [{"id": "nm0000123"}], "crew": []}},
        ),
    ]
    for title in odd:
        db_session.add(title)
    await db_session.flush()

    assert await taste.followed_title_ids(db_session, [t.id for t in odd], {1, 500}) == set()


def test_following_outweighs_language_but_not_similarity():
    """Ordering of the thumbs on the scale, stated as a test so a later
    tweak cannot silently invert it."""
    assert taste.FOLLOWED_BOOST > taste.LANGUAGE_BOOST
    assert taste.FOLLOWED_BOOST < 1.0, "a boost, not an override of the match itself"


async def test_follow_and_unfollow_round_trip(client, fake_idp, db_session, fake_tmdb_http):
    from sqlalchemy import select

    csrf = await sign_in(client, fake_idp, "fan")
    # TMDB is stubbed and has no person route, so the name falls back and
    # the follow still succeeds: being offline must not block it.
    followed = await client.post("/api/people/12345/follow", headers={"X-CSRF-Token": csrf})
    assert followed.status_code == 200
    assert followed.json() == {"following": True}

    listed = await client.get("/api/following")
    assert [p["person_id"] for p in listed.json()] == [12345]

    # Following twice is not an error and does not duplicate.
    again = await client.post("/api/people/12345/follow", headers={"X-CSRF-Token": csrf})
    assert again.status_code == 200
    user = (await db_session.execute(select(User).where(User.username == "fan"))).scalar_one()
    rows = (
        (await db_session.execute(select(FollowedPerson).where(FollowedPerson.user_id == user.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1

    gone = await client.delete("/api/people/12345/follow", headers={"X-CSRF-Token": csrf})
    assert gone.status_code == 204
    assert (await client.get("/api/following")).json() == []
    # Unfollowing something you do not follow is quietly fine.
    assert (
        await client.delete("/api/people/999/follow", headers={"X-CSRF-Token": csrf})
    ).status_code == 204


def test_search_extracts_people_and_ignores_everything_else():
    from app.routers.catalog import _people_from

    payload = {
        "results": [
            {"media_type": "movie", "id": 1, "title": "A Film"},
            {
                "media_type": "person",
                "id": 500,
                "name": "Someone",
                "profile_path": "/p.jpg",
                "known_for": [
                    {"title": "One"},
                    {"name": "Two"},
                    {"title": "Three"},
                    {"title": "Four"},
                ],
            },
            {"media_type": "person"},
        ]
    }
    people = _people_from(payload)
    assert len(people) == 1
    assert people[0].person_id == 500
    assert people[0].known_for == "One, Two, Three", "at most three, so a row stays readable"
    assert people[0].you_follow is False


def test_people_never_crowd_out_the_titles():
    from app.routers.catalog import _people_from

    payload = {
        "results": [
            {"media_type": "person", "id": i, "name": f"P{i}", "known_for": []} for i in range(30)
        ]
    }
    assert len(_people_from(payload)) == 8
