"""What the browser extension reports, and what the server does with it.

The title arrives scraped off a streaming page, so it carries decoration a
catalog never has. Getting the cleaning wrong pollutes a real history, which
is why it is deliberately conservative."""

import itertools

import pytest

from app.routers.extension import clean_title


class TestCleanTitle:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            # Observed on Prime Video.
            (
                "Prime Video: From Old Country Bumpkin to Master Swordsman II",
                "From Old Country Bumpkin to Master Swordsman II",
            ),
            # Observed on Shahid, where the slug arrives hyphenated.
            ("Ward-Ala-Foll-Wa-Yasmeen", "Ward Ala Foll Wa Yasmeen"),
            ("Watch Chernobyl | Netflix", "Chernobyl"),
            ("Inception", "Inception"),
        ],
    )
    def test_strips_what_players_add(self, raw, expected):
        assert clean_title(raw) == expected

    def test_keeps_hyphens_inside_a_real_name(self):
        """Spider-Man must not become Spider Man: the hyphen is part of the
        name, and only a slug has no spaces at all."""
        assert clean_title("Spider-Man: No Way Home") == "Spider-Man: No Way Home"

    def test_drops_episode_decoration(self):
        assert clean_title("Breaking Bad Season 2 Episode 5") == "Breaking Bad"
        assert clean_title("The Bear S01E03") == "The Bear"

    def test_picks_the_longest_part_not_the_service(self):
        assert clean_title("Shogun | Disney+") == "Shogun"
        assert clean_title("Disney+ | Shogun") == "Shogun"

    def test_survives_junk(self):
        assert clean_title("   ") == ""
        assert clean_title("|||") == ""


_next_id = itertools.count(700000)


async def _seed(db, name: str, kind: str = "movie", year: int | None = 2010):
    from app.models import Title

    title = Title(
        # A counter rather than a hash: two different names hashing into the
        # same slot made the fixture fail on the unique constraint.
        tmdb_id=next(_next_id),
        type=kind,
        name=name,
        year=year,
        genres=[],
        popularity=50.0,
    )
    db.add(title)
    await db.flush()
    return title


class TestMatching:
    async def test_exact_name_wins_over_a_longer_one(self, db_session):
        from app.routers.extension import _match

        await _seed(db_session, "The Order", year=2019)
        await _seed(db_session, "The Order of Things", year=2021)
        await db_session.commit()

        found = await _match(db_session, "The Order", 2019, "movie")
        assert found is not None and found.name == "The Order"

    async def test_a_short_partial_match_is_refused(self, db_session):
        """Better to log nothing than to log the wrong film."""
        from app.routers.extension import _match

        await _seed(db_session, "Dune: Part Two")
        await db_session.commit()

        assert await _match(db_session, "Dune", None, "movie") is None

    async def test_the_year_breaks_a_tie(self, db_session):
        from app.routers.extension import _match

        await _seed(db_session, "The Thing", year=1982)
        await _seed(db_session, "The Thing", year=2011)
        await db_session.commit()

        found = await _match(db_session, "The Thing", 1982, "movie")
        assert found is not None and found.year == 1982

    async def test_nothing_in_the_catalog_matches_nothing(self, db_session):
        from app.routers.extension import _match

        assert await _match(db_session, "A Film Nobody Has", 2024, "movie") is None


class TestActivity:
    async def test_a_view_is_recorded_but_not_a_watch(self, client, fake_idp, db_session):
        from sqlalchemy import func, select

        from app.models import Interaction, User, WatchEvent
        from tests.util import do_login

        await do_login(client, fake_idp, {"sub": "ext1", "preferred_username": "ext_viewer"})
        headers = {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}
        await _seed(db_session, "Arrival", year=2016)
        await db_session.commit()

        response = await client.post(
            "/api/extension/activity",
            json={"title": "Arrival", "site": "netflix", "year": 2016, "progress": 0.2},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["action"] == "viewed"

        user = (
            await db_session.execute(select(User).where(User.username == "ext_viewer"))
        ).scalar_one()
        watches = (
            await db_session.execute(
                select(func.count(WatchEvent.id)).where(WatchEvent.user_id == user.id)
            )
        ).scalar_one()
        views = (
            await db_session.execute(
                select(func.count(Interaction.id)).where(Interaction.user_id == user.id)
            )
        ).scalar_one()
        assert watches == 0, "a fifth of the way in is not watched"
        assert views == 1

    async def test_reaching_the_end_logs_it_once(self, client, fake_idp, db_session):
        from sqlalchemy import func, select

        from app.models import User, WatchEvent
        from tests.util import do_login

        await do_login(client, fake_idp, {"sub": "ext2", "preferred_username": "ext_finisher"})
        headers = {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}
        await _seed(db_session, "Whiplash", year=2014)
        await db_session.commit()

        for progress in (0.9, 0.94, 0.99):
            result = await client.post(
                "/api/extension/activity",
                json={"title": "Whiplash", "site": "prime", "year": 2014, "progress": progress},
                headers=headers,
            )
            assert result.status_code == 200

        user = (
            await db_session.execute(select(User).where(User.username == "ext_finisher"))
        ).scalar_one()
        watches = (
            await db_session.execute(
                select(func.count(WatchEvent.id)).where(WatchEvent.user_id == user.id)
            )
        ).scalar_one()
        assert watches == 1, "the credits rolling three times is still one viewing"

    async def test_an_unknown_title_says_so_rather_than_guessing(
        self, client, fake_idp, db_session
    ):
        from tests.util import do_login

        await do_login(client, fake_idp, {"sub": "ext3", "preferred_username": "ext_unknown"})
        headers = {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}

        response = await client.post(
            "/api/extension/activity",
            json={"title": "Some Show Nobody Indexed", "site": "osn", "progress": 0.95},
            headers=headers,
        )
        assert response.json() == {
            "matched": False,
            "name": None,
            "tmdb_id": None,
            "type": None,
            "poster_path": None,
            "action": "unmatched",
        }

    async def test_it_needs_a_token_or_a_session(self, client):
        response = await client.post(
            "/api/extension/activity", json={"title": "Anything", "site": "netflix"}
        )
        assert response.status_code == 401


class TestRealScrapes:
    """Names taken off an actual Prime Video watchlist, so the cleaner is
    checked against what these pages really produce rather than what a
    catalog would ideally contain."""

    @pytest.mark.parametrize(
        "scraped,expected",
        [
            ("Apocalypse Z: The Beginning of the End", "Apocalypse Z: The Beginning of the End"),
            ("Legally Blonde 2: Red, White And Blonde", "Legally Blonde 2: Red, White And Blonde"),
            ("The Mentalist - Season 2", "The Mentalist"),
            ("The Mentalist: The Complete First Season", "The Mentalist"),
            ("The Boys - Season 2", "The Boys"),
        ],
    )
    def test_prime_watchlist_names(self, scraped, expected):
        assert clean_title(scraped) == expected

    def test_a_colon_in_a_real_name_survives(self):
        """Box set phrasing is stripped, but a colon that is part of the
        title is not: the two look similar and only one should go."""
        assert clean_title("Spider-Man: No Way Home") == "Spider-Man: No Way Home"
        assert clean_title("Blade Runner 2049") == "Blade Runner 2049"


class TestListDeduplication:
    """A saved list carries one card per season. They are different cards
    with different names, and the same show."""

    async def test_two_seasons_of_one_show_match_once(self, client, fake_idp, db_session):
        from tests.util import do_login

        await do_login(client, fake_idp, {"sub": "dedup", "preferred_username": "dedup_user"})
        headers = {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}
        await _seed(db_session, "The Mentalist", kind="tv", year=2008)
        await db_session.commit()

        response = await client.post(
            "/api/extension/match",
            json={
                "site": "prime",
                "titles": [
                    {"title": "The Mentalist - Season 2"},
                    {"title": "The Mentalist: The Complete First Season"},
                    {"title": "The Mentalist - Season 3"},
                ],
            },
            headers=headers,
        )
        body = response.json()
        names = [r["name"] for r in body["results"] if r["matched"]]
        assert names == ["The Mentalist"], "three cards, one show, one row"
        assert body["matched"] == 1

    async def test_different_films_in_a_series_stay_separate(self, client, fake_idp, db_session):
        """Deduplicating must not collapse a franchise: these are two
        different films, not two cards for one."""
        from tests.util import do_login

        await do_login(client, fake_idp, {"sub": "dedup2", "preferred_username": "dedup_two"})
        headers = {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}
        await _seed(db_session, "Legally Blonde", year=2001)
        await _seed(db_session, "Legally Blonde 2: Red, White & Blonde", year=2003)
        await db_session.commit()

        response = await client.post(
            "/api/extension/match",
            json={
                "site": "prime",
                "titles": [
                    {"title": "Legally Blonde"},
                    {"title": "Legally Blonde 2: Red, White And Blonde"},
                ],
            },
            headers=headers,
        )
        assert response.json()["matched"] == 2
