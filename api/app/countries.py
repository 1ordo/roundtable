"""Which countries one person cares about.

`country_code` is the main one: the age rating shown, the default view.
`prefs["countries"]` is everywhere else they want covered. Availability,
cinema listings and release alerts read the whole set, because plenty of
people split their life across more than one place and a watchlist that
only knows about one of them is wrong half the time."""

from app.models import User

MAX_COUNTRIES = 10


def for_user(user: User) -> list[str]:
    """The main country first, then the rest, deduplicated.

    Order matters: the first is the one whose age rating is shown, so it
    must stay the primary even when others are listed."""
    out: list[str] = []
    if user.country_code:
        out.append(user.country_code.upper())
    for code in (user.prefs or {}).get("countries", []) or []:
        upper = str(code).strip().upper()[:2]
        if len(upper) == 2 and upper not in out:
            out.append(upper)
    return out[:MAX_COUNTRIES]
