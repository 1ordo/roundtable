"""One genre vocabulary across films and series.

TMDB keeps two. Films have Action, Adventure, Science Fiction and Fantasy;
series fold those into "Action & Adventure" and "Sci-Fi & Fantasy". So a
numeric genre id cannot survive switching between the two, and browsing both
at once has nothing to filter on.

This maps a single readable label to the genre *names* each side uses. Ids
are resolved from the live genre lists rather than hardcoded, so a renamed
or renumbered genre upstream does not silently produce an empty shelf."""

# label -> (names used for films, names used for series)
COMBINED: list[tuple[str, list[str], list[str]]] = [
    ("Action", ["Action", "Adventure"], ["Action & Adventure"]),
    ("Comedy", ["Comedy"], ["Comedy"]),
    ("Drama", ["Drama"], ["Drama"]),
    ("Thriller", ["Thriller", "Mystery"], ["Mystery"]),
    ("Horror", ["Horror"], []),
    ("Science fiction", ["Science Fiction"], ["Sci-Fi & Fantasy"]),
    ("Fantasy", ["Fantasy"], ["Sci-Fi & Fantasy"]),
    ("Animation", ["Animation"], ["Animation"]),
    ("Documentary", ["Documentary"], ["Documentary"]),
    ("Family", ["Family"], ["Family", "Kids"]),
    ("Crime", ["Crime"], ["Crime"]),
    ("Romance", ["Romance"], []),
    ("History", ["History"], []),
    ("War", ["War"], ["War & Politics"]),
    ("Western", ["Western"], ["Western"]),
    ("Music", ["Music"], []),
    ("Reality", [], ["Reality"]),
]


def _ids(names: list[str], live: list[dict]) -> list[int]:
    by_name = {str(g.get("name", "")).lower(): g.get("id") for g in live}
    out = []
    for name in names:
        found = by_name.get(name.lower())
        if found is not None:
            out.append(int(found))
    return out


def build(movie_genres: list[dict], tv_genres: list[dict]) -> list[dict]:
    """The labels worth showing, with the ids each side needs.

    A label with no ids on either side is dropped: offering a chip that
    can only ever return nothing is worse than not offering it."""
    out = []
    for label, movie_names, tv_names in COMBINED:
        movie_ids = _ids(movie_names, movie_genres)
        tv_ids = _ids(tv_names, tv_genres)
        if movie_ids or tv_ids:
            out.append({"name": label, "movie_ids": movie_ids, "tv_ids": tv_ids})
    return out


def resolve(label: str, media_type: str, combined: list[dict]) -> list[int]:
    """Ids for one label on one side. Empty means the side has no equivalent."""
    key = "movie_ids" if media_type == "movie" else "tv_ids"
    for entry in combined:
        if entry["name"].lower() == label.lower():
            ids: list[int] = entry[key]
            return ids
    return []
