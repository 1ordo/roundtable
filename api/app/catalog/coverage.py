"""Whether the source has anything to say about a service in a country.

There is a difference between "this film is not on Disney Plus in Egypt"
and "we have never heard of Disney Plus in Egypt", and everything in this
file exists because the app used to treat them as the same thing.

Egypt has eighteen thousand availability rows in the catalog: Netflix,
OSN+, Shahid, Apple TV. The data is there. What is not there is Disney
Plus, which has two rows across twenty-two thousand titles, because the
upstream provider does not model Disney Plus in Egypt at all. Somebody in
Cairo holding an Egyptian Disney Plus subscription was therefore told that
no Marvel film was on any service they had, and had them filtered out of
their own recommendations, on the strength of a gap in a dataset.

The check is not a list of countries and services maintained by hand. TMDB
publishes which providers operate in which region, so the question "do we
have data for this service here" is answered by the source itself: a
service missing from its own region list is unknown, not absent, and a
person who says they subscribe to it is better informed than we are.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import tmdb

logger = logging.getLogger("roundtable.coverage")


async def listed_in(db: AsyncSession, country: str) -> set[int] | None:
    """Provider ids the source says operate in this country.

    None when the answer is unavailable, which is not the same as an empty
    set: a failed lookup must never be read as "no providers here".
    """
    try:
        payload = await tmdb.provider_list(db, country)
    except (tmdb.TmdbNotConfigured, tmdb.TmdbError):
        logger.info("provider list unavailable for %s", country)
        return None
    results = payload.get("results") or []
    found = {int(p["provider_id"]) for p in results if p.get("provider_id") is not None}
    # An empty answer is a broken answer. No country has zero services, and
    # believing one does would mark every service the person owns unknown.
    return found or None


async def unlisted_services(
    db: AsyncSession, countries: list[str], service_ids: list[int]
) -> set[int]:
    """Of these services, the ones no country here is known to carry.

    A service listed in any one of the person's countries is covered: they
    can be told honestly where it is and is not. One listed in none of them
    is a hole in the data rather than a fact about the world.

    Returns an empty set when nothing could be checked, so a source outage
    changes nothing rather than silently widening every filter.
    """
    if not countries or not service_ids:
        return set()
    known: set[int] = set()
    checked = False
    for country in countries:
        listed = await listed_in(db, country)
        if listed is None:
            continue
        checked = True
        known |= listed
    if not checked:
        return set()
    return {sid for sid in service_ids if sid not in known}
