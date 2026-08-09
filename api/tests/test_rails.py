"""The personalized shelves: what earns a row, and what must never reach one."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.ai import rails
from app.models import Availability, Title, User, WatchEvent
from tests.util import do_login


def film(tmdb_id: int, name: str, released: str | None, genres=None, **kw) -> Title:
    raw = {"release_date": released} if released is not None else {}
    return Title(
        tmdb_id=tmdb_id,
        type="movie",
        name=name,
        genres=genres or [],
        poster_path=f"/{tmdb_id}.jpg",
        raw_tmdb=raw,
        **kw,
    )


async def test_a_film_only_in_cinemas_is_never_suggested(db_session):
    """The complaint this rule exists for: a film out last week, playing
    nowhere but cinemas, arriving at the top of "Picked for you"."""
    today = date.today()
    in_cinemas = film(1, "Out Last Week", (today - timedelta(days=6)).isoformat())
    unreleased = film(2, "Out Next Year", (today + timedelta(days=200)).isoformat())
    streaming = film(3, "On A Service", (today - timedelta(days=6)).isoformat())
    # Released a decade ago with nothing listed. An empty listing that old is
    # a gap in the crawl, not a statement that it is in cinemas, so it stays.
    old_and_unlisted = film(4, "Old And Unlisted", (today - timedelta(days=4000)).isoformat())
    for title in (in_cinemas, unreleased, streaming, old_and_unlisted):
        db_session.add(title)
    await db_session.flush()
    db_session.add(
        Availability(
            title_id=streaming.id,
            country="US",
            provider_id=8,
            provider_name="Somewhere",
            kind="stream",
        )
    )
    await db_session.flush()

    blocked = await rails.unwatchable_title_ids(db_session)
    assert in_cinemas.id in blocked, "released, listed nowhere: it is in cinemas"
    assert unreleased.id in blocked, "not out at all"
    assert streaming.id not in blocked
    assert old_and_unlisted.id not in blocked, "an old gap is not a cinema run"


async def test_a_series_still_airing_is_not_treated_as_a_cinema_release(db_session):
    """The zero-listings rule is about films. Series listings are patchier and
    a missing one says nothing, so only the date rules them out."""
    today = date.today()
    airing = Title(
        tmdb_id=10,
        type="tv",
        name="Airing Now",
        genres=[],
        poster_path="/10.jpg",
        raw_tmdb={"first_air_date": (today - timedelta(days=30)).isoformat()},
    )
    upcoming = Title(
        tmdb_id=11,
        type="tv",
        name="Next Year",
        genres=[],
        poster_path="/11.jpg",
        raw_tmdb={"first_air_date": (today + timedelta(days=90)).isoformat()},
    )
    db_session.add_all([airing, upcoming])
    await db_session.flush()

    blocked = await rails.unwatchable_title_ids(db_session)
    assert airing.id not in blocked
    assert upcoming.id in blocked


async def test_a_title_with_no_date_at_all_is_left_alone(db_session):
    """Missing dates are common in a catalog assembled from two providers.
    Treating absence as "in the future" would silently empty the shelves."""
    bare = film(20, "No Date", None)
    empty = film(21, "Empty Date", "")
    db_session.add_all([bare, empty])
    await db_session.flush()
    for title in (bare, empty):
        db_session.add(
            Availability(
                title_id=title.id, country="US", provider_id=8, provider_name="X", kind="stream"
            )
        )
    await db_session.flush()

    blocked = await rails.unwatchable_title_ids(db_session)
    assert bare.id not in blocked
    assert empty.id not in blocked


ACTION = {"id": 28, "name": "Action"}
DRAMA = {"id": 18, "name": "Drama"}
HORROR = {"id": 27, "name": "Horror"}


async def test_genre_shelves_follow_lift_not_raw_count(db_session, client, fake_idp):
    """Ranking your genres by how often you watch them answers "Drama" for
    everybody, because Drama is most of any catalog. Dividing by the
    catalog's own base rate answers what is distinctive about you."""
    rails._base_rates.clear()

    # A catalog that is overwhelmingly drama, with horror a rarity.
    for i in range(60):
        db_session.add(film(1000 + i, f"Drama {i}", "2015-01-01", genres=[DRAMA]))
    for i in range(4):
        db_session.add(film(2000 + i, f"Horror {i}", "2015-01-01", genres=[HORROR]))
    await db_session.flush()

    await do_login(client, fake_idp, {"sub": "sub-lift", "preferred_username": "lift"})
    user = (await db_session.execute(select(User).where(User.username == "lift"))).scalar_one()

    # They watch more drama than horror in absolute terms, but the horror is
    # far out of proportion to how much horror exists.
    dramas = (
        (await db_session.execute(select(Title).where(Title.name.like("Drama %")).limit(6)))
        .scalars()
        .all()
    )
    horrors = (
        (await db_session.execute(select(Title).where(Title.name.like("Horror %")))).scalars().all()
    )
    now = datetime.now(UTC)
    for title in list(dramas) + list(horrors):
        db_session.add(WatchEvent(user_id=user.id, title_id=title.id, watched_at=now))
    await db_session.flush()

    ranked = await rails.affinity_genres(db_session, user, "movie")
    names = [name for _, name in ranked]
    assert "Horror" in names, "four of four horror films watched is a strong signal"
    assert names[0] == "Horror", f"horror should lead on lift, got {names}"
    rails._base_rates.clear()


async def test_a_genre_watched_once_does_not_earn_a_shelf(db_session, client, fake_idp):
    """One horror film in a history of forty is not a horror shelf."""
    rails._base_rates.clear()
    for i in range(40):
        db_session.add(film(3000 + i, f"Action {i}", "2015-01-01", genres=[ACTION]))
    db_session.add(film(3999, "One Horror", "2015-01-01", genres=[HORROR]))
    await db_session.flush()

    await do_login(client, fake_idp, {"sub": "sub-once", "preferred_username": "once"})
    user = (await db_session.execute(select(User).where(User.username == "once"))).scalar_one()

    now = datetime.now(UTC)
    actions = (
        (await db_session.execute(select(Title).where(Title.name.like("Action %")).limit(10)))
        .scalars()
        .all()
    )
    one_horror = (
        await db_session.execute(select(Title).where(Title.name == "One Horror"))
    ).scalar_one()
    for title in list(actions) + [one_horror]:
        db_session.add(WatchEvent(user_id=user.id, title_id=title.id, watched_at=now))
    await db_session.flush()

    names = [name for _, name in await rails.affinity_genres(db_session, user, "movie")]
    assert "Horror" not in names, f"a single watch is not an affinity, got {names}"
    rails._base_rates.clear()


@pytest.mark.parametrize("count", [0, rails.MIN_SHELF - 1])
def test_a_shelf_too_short_to_be_useful_is_dropped(count):
    """Half a row reads as an apology. Better to have fewer shelves."""
    shelves: list[rails.Shelf] = []
    used: set = set()
    rails._add(shelves, used, "k", "A shelf", [object()] * count)  # type: ignore[list-item]
    assert shelves == []
    assert used == set()


def test_the_main_shelf_is_longer_than_it_was():
    """The complaint was that the shelf ran out. Stated as a test so a later
    tidy-up cannot quietly put it back."""
    assert rails.MAIN_SHELF >= 40
    assert rails.POOL >= rails.MAIN_SHELF * 4, (
        "a pool that only fills the main shelf feeds no others"
    )
