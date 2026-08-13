"""Franchise watch-order, which is a catalog question rather than an AI one.

The reason this is deterministic at all: a language model asked to list the
MCU in order returns a plausible list with the wrong order and entries
missing, and there is no way to tell from the output which. These tests pin
the parts that decide correctness.
"""

from datetime import date

from app.catalog import universes, watch_order


class TestNamingAFranchise:
    def test_the_longest_alias_wins(self):
        """ "marvel cinematic universe" contains "marvel". Matching the short
        alias would answer a specific question with a broader list."""
        found = universes.find("show me the marvel cinematic universe in order")
        assert found is not None and found.key == "mcu"

    def test_a_plain_mention_still_resolves(self):
        found = universes.find("i wanna watch marvel movies from a to z")
        assert found is not None and found.key == "mcu"

    def test_an_unknown_franchise_is_not_forced_into_one(self):
        assert universes.find("the fast and the furious") is None
        assert universes.find("") is None

    def test_a_title_finds_its_universe_by_keyword(self):
        """The path for "what leads into the last Spider-Man": resolve the
        film, read its keywords, widen to the franchise."""
        assert universes.for_keyword_ids({180547, 9715}).key == "mcu"
        assert universes.for_keyword_ids({9715}) is None

    def test_collections_are_not_duplicated_in_the_registry(self):
        """Anything TMDB models as a collection must resolve as one. Listing
        it here too creates two sources of truth that will disagree."""
        for universe in universes.UNIVERSES:
            assert universe.keywords or universe.companies, (
                f"{universe.key} has no filter, so it is really a collection"
            )


class TestOrdering:
    def test_release_order_uses_the_date_not_the_year(self):
        """The bug this replaces: four MCU films shipped in 2021, and sorting
        by year left their order to whatever TMDB happened to return."""
        titles = [
            watch_order.OrderedTitle(3, "movie", "Eternals", 2021, date(2021, 11, 3), None, None),
            watch_order.OrderedTitle(1, "movie", "Widow", 2021, date(2021, 7, 7), None, None),
            watch_order.OrderedTitle(2, "movie", "Shang-Chi", 2021, date(2021, 9, 1), None, None),
        ]
        assert [t.name for t in watch_order._sorted(titles)] == [
            "Widow",
            "Shang-Chi",
            "Eternals",
        ]

    def test_something_undated_sorts_last(self):
        """An announced-but-unreleased entry is not where a watch-through
        starts, and None sorting first would put it there."""
        titles = [
            watch_order.OrderedTitle(2, "movie", "Announced", None, None, None, None),
            watch_order.OrderedTitle(1, "movie", "Out", 2019, date(2019, 4, 1), None, None),
        ]
        assert [t.name for t in watch_order._sorted(titles)] == ["Out", "Announced"]

    def test_a_bad_date_does_not_break_the_order(self):
        assert watch_order._as_date("not a date") is None
        assert watch_order._as_date("") is None
        assert watch_order._as_date("2021-11-03T00:00:00Z") == date(2021, 11, 3)


class TestTheEndpoint:
    async def test_it_needs_something_to_go_on(self, client, fake_idp, tmdb_key):
        from tests.util import LORDO, do_login

        await do_login(client, fake_idp, LORDO)
        assert (await client.get("/api/watch-order")).status_code == 422

    async def test_an_unknown_franchise_is_a_404_not_a_500(
        self, client, fake_idp, fake_tmdb_http, tmdb_key
    ):
        """ "I do not know that franchise" is an answer, not a failure."""
        from tests.util import LORDO, do_login

        await do_login(client, fake_idp, LORDO)
        resp = await client.get("/api/watch-order", params={"q": "a franchise that is not real"})
        assert resp.status_code == 404

    async def test_it_is_behind_a_login(self, client):
        assert (await client.get("/api/watch-order", params={"q": "marvel"})).status_code == 401


class TestPickingTheRightCollection:
    """Asked for "star wars", the resolver answered with The Ewok Adventures.

    The local table was checked first to save a search, but the check was a
    substring match with no ordering, so it returned whichever row Postgres
    reached first. Both of these are honest matches for "star wars" and
    neither is the franchise anybody meant. Same for "batman", which found
    The Batman Collection: one film, from 2022.
    """

    def test_the_collection_actually_called_this_wins(self):
        candidates = [
            (133830, "Star Wars: The Ewok Adventures Collection"),
            (10, "Star Wars Collection"),
            (302331, "LEGO Star Wars Collection"),
        ]
        assert watch_order._exact_match("star wars", candidates) == 10

    def test_a_substring_match_alone_is_not_enough(self):
        """Nothing here IS "star wars", so the caller has to go and search
        rather than settle for the nearest row it happens to hold."""
        candidates = [
            (133830, "Star Wars: The Ewok Adventures Collection"),
            (302331, "LEGO Star Wars Collection"),
        ]
        assert watch_order._exact_match("star wars", candidates) is None

    def test_the_bookkeeping_word_is_not_part_of_the_name(self):
        assert watch_order._exact_match("harry potter", [(1241, "Harry Potter Collection")]) == 1241

    def test_matching_ignores_case_and_spacing(self):
        assert watch_order._exact_match("  STAR   wars ", [(10, "Star Wars Collection")]) == 10

    def test_an_empty_query_matches_nothing(self):
        """Otherwise a collection named "Collection" would answer for it."""
        assert watch_order._exact_match("", [(1, "Collection")]) is None
