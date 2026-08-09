"""Browse across both media types with one shared genre vocabulary."""

from app.catalog import genre_map

MOVIE_GENRES = [
    {"id": 28, "name": "Action"},
    {"id": 12, "name": "Adventure"},
    {"id": 878, "name": "Science Fiction"},
    {"id": 27, "name": "Horror"},
]
TV_GENRES = [
    {"id": 10759, "name": "Action & Adventure"},
    {"id": 10765, "name": "Sci-Fi & Fantasy"},
    {"id": 10764, "name": "Reality"},
]


def test_one_label_resolves_to_the_ids_each_side_actually_uses():
    combined = genre_map.build(MOVIE_GENRES, TV_GENRES)
    names = [c["name"] for c in combined]
    assert "Action" in names and "Horror" in names and "Reality" in names

    assert sorted(genre_map.resolve("Action", "movie", combined)) == [12, 28]
    assert genre_map.resolve("Action", "tv", combined) == [10759]
    # Films and series disagree here, and the label still works on both.
    assert genre_map.resolve("Science fiction", "movie", combined) == [878]
    assert genre_map.resolve("Science fiction", "tv", combined) == [10765]


def test_a_label_with_no_equivalent_returns_nothing_rather_than_everything():
    combined = genre_map.build(MOVIE_GENRES, TV_GENRES)
    # Series have no Horror genre upstream.
    assert genre_map.resolve("Horror", "tv", combined) == []
    assert genre_map.resolve("Reality", "movie", combined) == []


def test_labels_with_no_ids_on_either_side_are_not_offered():
    combined = genre_map.build([], TV_GENRES)
    assert all(c["movie_ids"] or c["tv_ids"] for c in combined)
    assert "Horror" not in [c["name"] for c in combined]


async def test_browse_offline_covers_both_types_and_sorts(client, fake_idp, db_session):
    from datetime import UTC, datetime

    from app.catalog import local
    from app.models import Title

    db_session.add_all(
        [
            Title(
                tmdb_id=1,
                type="movie",
                name="Loud Film",
                genres=[{"id": 28, "name": "Action"}],
                popularity=90.0,
                tmdb_rating=6.0,
                tmdb_votes=900,
                year=1999,
                details_refreshed_at=datetime.now(UTC),
            ),
            Title(
                tmdb_id=2,
                type="tv",
                name="Loud Show",
                genres=[{"id": 10759, "name": "Action & Adventure"}],
                popularity=95.0,
                tmdb_rating=9.0,
                tmdb_votes=900,
                year=2024,
                details_refreshed_at=datetime.now(UTC),
            ),
            Title(
                tmdb_id=3,
                type="movie",
                name="Quiet Film",
                genres=[{"id": 18, "name": "Drama"}],
                popularity=10.0,
                tmdb_rating=8.0,
                tmdb_votes=900,
                year=2001,
                details_refreshed_at=datetime.now(UTC),
            ),
        ]
    )
    await db_session.commit()

    both = await local.browse(db_session, None, [], "popular")
    assert {t.name for t in both} == {"Loud Film", "Loud Show", "Quiet Film"}

    # The film and series ids for the same label, together.
    action = await local.browse(db_session, None, [28, 10759], "popular")
    assert [t.name for t in action] == ["Loud Show", "Loud Film"]

    top = await local.browse(db_session, None, [], "top")
    assert top[0].name == "Loud Show"

    newest = await local.browse(db_session, None, [], "new")
    assert newest[0].name == "Loud Show"

    films_only = await local.browse(db_session, "movie", [], "popular")
    assert all(t.type == "movie" for t in films_only)
