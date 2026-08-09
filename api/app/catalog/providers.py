"""Click-out links. The app never plays DRM content; it hands the viewer to
the provider. Known providers get a direct search deep link; everything else
falls back to the TMDB/JustWatch page for the title in that country."""

from urllib.parse import quote

SEARCH_BY_NAME = {
    "netflix": "https://www.netflix.com/search?q={q}",
    "amazon prime video": "https://www.primevideo.com/search?phrase={q}",
    "disney plus": "https://www.disneyplus.com/search?q={q}",
    "apple tv plus": "https://tv.apple.com/search?term={q}",
    "apple tv": "https://tv.apple.com/search?term={q}",
    "max": "https://play.max.com/search?q={q}",
    "hbo max": "https://play.max.com/search?q={q}",
    "hulu": "https://www.hulu.com/search?q={q}",
    "paramount plus": "https://www.paramountplus.com/search/{q}/",
    "crunchyroll": "https://www.crunchyroll.com/search?q={q}",
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "google play movies": "https://play.google.com/store/search?q={q}&c=movies",
    "shahid vip": "https://shahid.mbc.net/en/search?q={q}",
    "osn+": "https://www.osnplus.com/en/search?q={q}",
    "starzplay": "https://starzplay.com/en/search?q={q}",
    "watch it": "https://www.watchit.com/en/search?q={q}",
}


def click_out_url(provider_name: str, title_name: str, fallback_link: str | None) -> str | None:
    template = SEARCH_BY_NAME.get(provider_name.strip().lower())
    if template:
        return template.format(q=quote(title_name))
    return fallback_link
