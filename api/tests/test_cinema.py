"""The cinema tracker: dates, the run window, and the booking alert."""

from datetime import UTC, date, datetime, timedelta

from app.routers import cinema

# Trimmed from a real TMDB release_dates payload.
RELEASES = {
    "release_dates": {
        "results": [
            {
                "iso_3166_1": "US",
                "release_dates": [
                    {"type": 1, "release_date": "2026-01-05T00:00:00.000Z"},  # premiere
                    {"type": 3, "release_date": "2026-02-10T00:00:00.000Z"},  # theatrical
                    {"type": 4, "release_date": "2026-05-01T00:00:00.000Z"},  # digital
                ],
            },
            {
                "iso_3166_1": "EG",
                "release_dates": [{"type": 3, "release_date": "2026-04-01T00:00:00.000Z"}],
            },
        ]
    }
}


def test_the_date_is_the_one_for_your_country():
    assert cinema.theatrical_date(RELEASES, "US") == date(2026, 2, 10)
    assert cinema.theatrical_date(RELEASES, "EG") == date(2026, 4, 1)


def test_a_country_with_no_listing_gets_no_date_rather_than_a_wrong_one():
    """Someone will plan an evening around this, so borrowing another
    country's date is worse than admitting we do not know."""
    assert cinema.theatrical_date(RELEASES, "JP") is None
    assert cinema.theatrical_date(RELEASES, None) is None
    assert cinema.theatrical_date({}, "US") is None


def test_only_theatrical_release_types_count():
    """A premiere is not a release you can buy a ticket for, and a digital
    date is the opposite of a cinema date."""
    premiere_only = {
        "release_dates": {
            "results": [
                {
                    "iso_3166_1": "US",
                    "release_dates": [
                        {"type": 1, "release_date": "2026-01-05T00:00:00.000Z"},
                        {"type": 4, "release_date": "2026-05-01T00:00:00.000Z"},
                    ],
                }
            ]
        }
    }
    assert cinema.theatrical_date(premiere_only, "US") is None


def test_the_earliest_theatrical_date_wins():
    """A limited run before the wide one is still the day you can go."""
    both = {
        "release_dates": {
            "results": [
                {
                    "iso_3166_1": "US",
                    "release_dates": [
                        {"type": 3, "release_date": "2026-02-10T00:00:00.000Z"},
                        {"type": 2, "release_date": "2026-01-25T00:00:00.000Z"},
                    ],
                }
            ]
        }
    }
    assert cinema.theatrical_date(both, "US") == date(2026, 1, 25)


def test_a_malformed_date_is_skipped_not_fatal():
    broken = {
        "release_dates": {
            "results": [
                {
                    "iso_3166_1": "US",
                    "release_dates": [
                        {"type": 3, "release_date": "not a date"},
                        {"type": 3, "release_date": "2026-02-10T00:00:00.000Z"},
                    ],
                }
            ]
        }
    }
    assert cinema.theatrical_date(broken, "US") == date(2026, 2, 10)


def test_the_run_window_opens_on_the_day_and_closes_after_eight_weeks():
    opens = date(2026, 3, 1)
    assert cinema.is_showing(opens, opens) is True, "the opening day counts"
    assert cinema.is_showing(opens, opens - timedelta(days=1)) is False
    assert cinema.is_showing(opens, opens + timedelta(weeks=8)) is True
    assert cinema.is_showing(opens, opens + timedelta(weeks=8, days=1)) is False
    assert cinema.is_showing(None, opens) is False


def test_the_alert_window_opens_a_week_early_and_stays_open_to_the_end():
    """The alert is meant to leave time to make a plan, so it starts a week
    out. The far edge matters too: a film tracked after it opened should
    still get its one alert rather than miss the window entirely."""
    opens = date(2026, 3, 1)
    week_before = opens - timedelta(days=cinema.LEAD_DAYS)

    assert cinema.alert_due(opens, week_before) is True, "a week out is the point"
    assert cinema.alert_due(opens, week_before - timedelta(days=1)) is False, "not yet"
    assert cinema.alert_due(opens, opens) is True
    assert cinema.alert_due(opens, opens + timedelta(weeks=8)) is True, "tracked late still counts"
    assert cinema.alert_due(opens, opens + timedelta(weeks=8, days=1)) is False
    assert cinema.alert_due(None, opens) is False


async def test_an_alert_fires_a_week_ahead_and_only_once(
    client, fake_idp, db_session, fake_tmdb_http, tmdb_key
):
    """The job had no coverage at all, which is how it kept its old
    behaviour through a rewrite. Both halves matter: it must fire, and it
    must not fire twice."""
    from sqlalchemy import select

    from app.models import List, ListItem, Notification, Title, User
    from tests.util import do_login

    await do_login(client, fake_idp, {"sub": "s-alert", "preferred_username": "planner"})
    person = (await db_session.execute(select(User).where(User.username == "planner"))).scalar_one()
    person.country_code = "US"

    opens = datetime.now(UTC).date() + timedelta(days=cinema.LEAD_DAYS)
    title = Title(
        tmdb_id=999501,
        type="movie",
        name="Something Worth Booking",
        raw_tmdb={
            "release_dates": {
                "results": [
                    {
                        "iso_3166_1": "US",
                        "release_dates": [{"type": 3, "release_date": f"{opens.isoformat()}"}],
                    }
                ]
            }
        },
    )
    db_session.add(title)
    await db_session.flush()

    listing = List(
        tenant_id=person.tenant_id,
        user_id=person.id,
        name="Cinema",
        kind=cinema.CINEMA_LIST,
    )
    db_session.add(listing)
    await db_session.flush()
    db_session.add(ListItem(list_id=listing.id, title_id=title.id))
    await db_session.commit()

    first = await cinema.alert_on_openings(db_session)
    assert first["notified"] == 1, "a film a week out should be announced"

    sent = (
        (
            await db_session.execute(
                select(Notification).where(
                    Notification.user_id == person.id, Notification.kind == "cinema"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(sent) == 1
    assert "opens in cinemas" in sent[0].message, "it has not opened yet, so do not say it has"

    second = await cinema.alert_on_openings(db_session)
    assert second["notified"] == 0, "once per film, not once per run"


async def test_tracking_a_film_and_untracking_it(
    client, fake_idp, db_session, fake_tmdb_http, tmdb_key
):
    from tests.util import do_login

    await do_login(client, fake_idp, {"sub": "s-c", "preferred_username": "cinemagoer"})
    csrf = (await client.get("/api/me")).json()["csrf"]

    tracked = await client.post(
        "/api/cinema/track",
        json={"type": "movie", "tmdb_id": 354912},
        headers={"X-CSRF-Token": csrf},
    )
    assert tracked.status_code == 200
    assert tracked.json()["tracked"] is True

    page = await client.get("/api/cinema")
    assert [t["card"]["name"] for t in page.json()["tracking"]] == ["Coco"]

    # Tracking twice does not duplicate.
    await client.post(
        "/api/cinema/track",
        json={"type": "movie", "tmdb_id": 354912},
        headers={"X-CSRF-Token": csrf},
    )
    assert len((await client.get("/api/cinema")).json()["tracking"]) == 1

    gone = await client.delete(
        "/api/cinema/track?type=movie&tmdb_id=354912", headers={"X-CSRF-Token": csrf}
    )
    assert gone.status_code == 204
    assert (await client.get("/api/cinema")).json()["tracking"] == []


async def test_series_cannot_be_tracked_for_a_cinema(client, fake_idp, db_session):
    from tests.util import do_login

    await do_login(client, fake_idp, {"sub": "s-t", "preferred_username": "tv"})
    csrf = (await client.get("/api/me")).json()["csrf"]
    refused = await client.post(
        "/api/cinema/track", json={"type": "tv", "tmdb_id": 456}, headers={"X-CSRF-Token": csrf}
    )
    assert refused.status_code == 422


def test_on_now_covers_the_run_window_only():
    """A revival screening of a 1977 film is not what someone means by what
    is on now, and mixing them in is what made the shelf look wrong."""
    today = date(2026, 8, 1)
    run_start = today - timedelta(weeks=cinema.RUN_WEEKS)

    # Released inside the window: a current run.
    assert cinema.is_showing(run_start + timedelta(days=1), today) is True
    # Released the day the window opens: still counts.
    assert cinema.is_showing(run_start, today) is True
    # Older than the window: the run is over, whatever the listing says.
    assert cinema.is_showing(run_start - timedelta(days=1), today) is False
    assert cinema.is_showing(date(1977, 10, 19), today) is False
