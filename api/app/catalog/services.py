"""The streaming services people here can subscribe to.

TMDB lists a provider under several ids: a different one per region, plus
separate entries for ad tiers and channel resellers. Each service below
carries every id it answers to, so availability matches whatever TMDB
reports for Egypt, Morocco, or anywhere else. Ids verified against
/watch/providers/movie.
"""

SERVICES: list[dict] = [
    {
        "id": 8,
        "name": "Netflix",
        "color": "#e50914",
        # Standard with ads, and the kids profile.
        "ids": [8, 1796, 175],
        "search": "https://www.netflix.com/search?q=",
    },
    {
        "id": 9,
        "name": "Prime Video",
        "color": "#00a8e1",
        "note": "with MGM+",
        # 119 is the id used across Egypt, Morocco and much of EMEA.
        "ids": [9, 119, 2100, 613, 34, 583, 588, 2141],
        "search": "https://www.primevideo.com/search/ref=atv_nb_sr?phrase=",
    },
    {
        "id": 337,
        "name": "Disney+",
        "color": "#113ccf",
        "note": "with Hulu",
        "ids": [337, 122, 15, 508],
        "search": "https://www.disneyplus.com/search?q=",
    },
    {
        "id": 1899,
        "name": "HBO Max",
        "color": "#8b5cf6",
        "note": "with Discovery+",
        "ids": [1899, 483, 1825, 510, 520, 584],
        "search": "https://www.hbomax.com/search?q=",
    },
    {
        "id": 350,
        "name": "Apple TV+",
        "color": "#a2aaad",
        "ids": [350, 2243],
        "search": "https://tv.apple.com/search?term=",
    },
    {
        "id": 531,
        "name": "Paramount+",
        "color": "#0064ff",
        "ids": [531, 1853],
        "search": "https://www.paramountplus.com/search/?q=",
    },
    {
        "id": 386,
        "name": "Peacock",
        "color": "#ffc700",
        "ids": [386, 387],
        "search": "https://www.peacocktv.com/search?q=",
    },
    {
        "id": 1715,
        "name": "Shahid",
        "color": "#00c389",
        "ids": [1715],
        "search": "https://shahid.mbc.net/en/search?q=",
    },
    {
        "id": 2199,
        "name": "Watch It",
        "color": "#f5a623",
        "ids": [2199],
        "search": "https://www.watchit.com/search?q=",
    },
    # The catalog carries availability for both of these, and the browser
    # extension has adapters for both, so leaving them off the list meant a
    # subscription that could never be ticked and therefore never filtered on.
    # Crunchyroll's Amazon channel is folded in, the way Peacock's is.
    {
        "id": 15,
        "name": "Hulu",
        "color": "#1ce783",
        "ids": [15],
        "search": "https://www.hulu.com/search?q=",
    },
    {
        "id": 283,
        "name": "Crunchyroll",
        "color": "#f47521",
        "ids": [283, 1968],
        "search": "https://www.crunchyroll.com/search?q=",
    },
    # Regional services TMDB actually reports in Egypt and Morocco.
    {
        "id": 629,
        "name": "OSN+",
        "color": "#7b3fe4",
        "ids": [629],
        "search": "https://www.osnplus.com/en-eg/search?q=",
    },
    {
        "id": 630,
        "name": "STARZPLAY",
        "color": "#00b3a4",
        "ids": [630],
        "search": "https://starzplay.com/search?q=",
    },
]

BY_ID = {service["id"]: service for service in SERVICES}

# Every provider id, however TMDB spells it, back to the service it belongs to.
ALIASES: dict[int, dict] = {
    provider_id: service for service in SERVICES for provider_id in service["ids"]
}


def provider_ids_for(service_id: int) -> list[int]:
    service = BY_ID.get(service_id)
    return list(service["ids"]) if service else [service_id]


def service_for_provider(provider_id: int) -> dict | None:
    return ALIASES.get(provider_id)


def search_url(provider_id: int, title_name: str) -> str | None:
    from urllib.parse import quote_plus

    service = ALIASES.get(provider_id) or BY_ID.get(provider_id)
    if service is None:
        return None
    return service["search"] + quote_plus(title_name)
