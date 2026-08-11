"""Franchises that are bigger than one TMDB collection.

TMDB models a "collection" as a set of sequels: Harry Potter is one, each
Spider-Man series is one. That covers most of what people ask for, and
app.catalog.watch_order tries it first.

It does not cover the Marvel Cinematic Universe, which is not a collection
at all: it is dozens of films across several collections plus standalone
entries, and the only thing that groups them is a keyword and a studio.
Nor Star Wars, where the films are a collection but the series that sit
between them are not, because collections are movie-only.

So this file is a small registry of the handful of franchises that need a
discover query rather than a collection id. It is editorial, deliberately.
The alternative is asking a language model to list the MCU in order, which
returns a plausible list with the wrong order and two films missing. Twenty
lines of reviewable data in git, whose correctness a person can check, beats
a confident guess.

Each entry is a filter, not a list of titles, so a franchise that gains a
film next year gains it here without an edit.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Universe:
    """One franchise, expressed as a TMDB discover filter."""

    key: str
    name: str
    # What someone might type. Matched case-insensitively, longest first, so
    # "marvel cinematic universe" wins over "marvel".
    aliases: tuple[str, ...]
    # TMDB keyword ids. The MCU keyword is the thing that actually holds it
    # together; the company alone catches Marvel's pre-MCU output.
    keywords: tuple[int, ...] = ()
    # TMDB company ids, used with the keyword rather than instead of it.
    companies: tuple[int, ...] = ()
    # Documentaries and making-ofs carry the same keyword and are not part of
    # anybody's watch-through. 99 is Documentary.
    without_genres: tuple[int, ...] = (99,)
    # Specials and featurettes hide under the same keyword. Verified: this
    # cutoff keeps every feature and drops the extras.
    min_runtime: int = 70
    include_tv: bool = True
    note: str = ""
    seeds: tuple[str, ...] = field(default_factory=tuple)


# Seeded with the franchises that genuinely cannot be resolved as a
# collection. Anything TMDB models as a collection must NOT be added here:
# watch_order finds those on its own, and duplicating them means two sources
# of truth that will disagree.
UNIVERSES: tuple[Universe, ...] = (
    Universe(
        key="mcu",
        name="Marvel Cinematic Universe",
        aliases=(
            "marvel cinematic universe",
            "mcu",
            "marvel movies",
            "marvel films",
            "marvel",
        ),
        keywords=(180547,),
        companies=(420,),
        note=(
            "Release order. The MCU is not a TMDB collection, so this is the "
            "keyword Marvel Studios tags its own entries with, narrowed to "
            "features."
        ),
    ),
    Universe(
        key="dceu",
        name="DC Extended Universe",
        aliases=("dc extended universe", "dceu", "dc movies", "dc films"),
        keywords=(229266,),
        companies=(429,),
        note="Release order, features only.",
    ),
    Universe(
        key="wizarding-world",
        name="Wizarding World",
        aliases=(
            "wizarding world",
            "harry potter and fantastic beasts",
            "the whole harry potter universe",
        ),
        keywords=(616,),
        note=(
            "Harry Potter plus Fantastic Beasts. Plain 'harry potter' is a "
            "TMDB collection and resolves without this entry."
        ),
    ),
)


def find(name: str) -> Universe | None:
    """Match what someone typed to a universe, longest alias first.

    Longest first matters: "marvel cinematic universe" contains "marvel",
    and matching the short one would answer a specific question with a
    broader list.
    """
    text = " ".join((name or "").lower().split())
    if not text:
        return None
    best: tuple[int, Universe] | None = None
    for universe in UNIVERSES:
        for alias in universe.aliases:
            if alias in text and (best is None or len(alias) > best[0]):
                best = (len(alias), universe)
    return best[1] if best else None


def for_keyword_ids(keyword_ids: set[int]) -> Universe | None:
    """Which universe a title belongs to, from its own TMDB keyword ids.

    This is the path for "what leads into this one": resolve the film, look
    at what it is tagged with, and widen to the franchise around it.
    """
    for universe in UNIVERSES:
        if keyword_ids & set(universe.keywords):
            return universe
    return None
