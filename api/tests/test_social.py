"""Friends, privacy, and the whole watch night flow."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import Notification, Title, User, WatchEvent, WatchNight
from tests.util import do_login


async def sign_in(client, fake_idp, name: str) -> str:
    """Log in as someone and return their CSRF token."""
    await do_login(client, fake_idp, {"sub": f"sub-{name}", "preferred_username": name})
    return (await client.get("/api/me")).json()["csrf"]


async def seed_title(db_session, tmdb_id: int, name: str) -> Title:
    title = Title(tmdb_id=tmdb_id, type="movie", name=name, genres=[], poster_path="/p.jpg")
    db_session.add(title)
    await db_session.commit()
    return title


async def test_a_friendship_needs_both_sides(client, fake_idp, db_session):
    csrf_a = await sign_in(client, fake_idp, "ana")
    sent = await client.post(
        "/api/friends/request", json={"username": "bo"}, headers={"X-CSRF-Token": csrf_a}
    )
    assert sent.status_code == 404, "cannot befriend an account that does not exist"

    csrf_b = await sign_in(client, fake_idp, "bo")
    csrf_a = await sign_in(client, fake_idp, "ana")
    sent = await client.post(
        "/api/friends/request", json={"username": "bo"}, headers={"X-CSRF-Token": csrf_a}
    )
    assert sent.status_code == 201
    assert sent.json()["status"] == "pending"

    # Until Bo agrees, they are not friends.
    mine = (await client.get("/api/friends")).json()
    assert mine["friends"] == []
    assert [p["username"] for p in mine["outgoing"]] == ["bo"]

    csrf_b = await sign_in(client, fake_idp, "bo")
    theirs = (await client.get("/api/friends")).json()
    assert [p["username"] for p in theirs["incoming"]] == ["ana"]

    accepted = await client.post("/api/friends/ana/accept", headers={"X-CSRF-Token": csrf_b})
    assert accepted.status_code == 200
    theirs = (await client.get("/api/friends")).json()
    assert [p["username"] for p in theirs["friends"]] == ["ana"]
    assert theirs["incoming"] == []


async def test_asking_back_is_the_same_as_accepting(client, fake_idp, db_session):
    await sign_in(client, fake_idp, "cy")
    csrf_d = await sign_in(client, fake_idp, "di")
    await client.post(
        "/api/friends/request", json={"username": "cy"}, headers={"X-CSRF-Token": csrf_d}
    )
    csrf_c = await sign_in(client, fake_idp, "cy")
    # Cy has a pending request from Di and presses "add" rather than
    # "accept". Meaning the same thing, it should have the same result.
    again = await client.post(
        "/api/friends/request", json={"username": "di"}, headers={"X-CSRF-Token": csrf_c}
    )
    assert again.json()["status"] == "friends"


async def test_profiles_are_private_until_made_public(client, fake_idp, db_session):
    from app.routers.friends import can_view

    await sign_in(client, fake_idp, "eve")
    csrf = await sign_in(client, fake_idp, "fin")
    eve = (await db_session.execute(select(User).where(User.username == "eve"))).scalar_one()
    fin = (await db_session.execute(select(User).where(User.username == "fin"))).scalar_one()

    assert await can_view(db_session, fin, eve) is False, (
        "friends only by default, and they are not friends"
    )
    assert await can_view(db_session, eve, eve) is True, "always your own"

    await client.put("/api/me", json={"visibility": "public"}, headers={"X-CSRF-Token": csrf})
    await db_session.refresh(fin)
    assert await can_view(db_session, eve, fin) is True


async def test_friends_can_see_each_other_without_going_public(client, fake_idp, db_session):
    from app.routers.friends import can_view

    await sign_in(client, fake_idp, "gus")
    csrf_h = await sign_in(client, fake_idp, "hal")
    await client.post(
        "/api/friends/request", json={"username": "gus"}, headers={"X-CSRF-Token": csrf_h}
    )
    csrf_g = await sign_in(client, fake_idp, "gus")
    await client.post("/api/friends/hal/accept", headers={"X-CSRF-Token": csrf_g})

    gus = (await db_session.execute(select(User).where(User.username == "gus"))).scalar_one()
    hal = (await db_session.execute(select(User).where(User.username == "hal"))).scalar_one()
    await db_session.refresh(gus)
    await db_session.refresh(hal)
    assert hal.visibility == "friends" and gus.visibility == "friends"
    assert await can_view(db_session, gus, hal) is True
    assert await can_view(db_session, hal, gus) is True


async def test_you_can_only_invite_friends_to_a_night(client, fake_idp, db_session):
    await sign_in(client, fake_idp, "ivy")
    csrf = await sign_in(client, fake_idp, "jo")
    refused = await client.post(
        "/api/nights",
        json={"name": "Friday", "invite": ["ivy"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert refused.status_code == 403
    assert "friends" in refused.json()["detail"]


async def make_friends(client, fake_idp, one: str, two: str) -> None:
    csrf = await sign_in(client, fake_idp, one)
    await client.post(
        "/api/friends/request", json={"username": two}, headers={"X-CSRF-Token": csrf}
    )
    csrf = await sign_in(client, fake_idp, two)
    await client.post(f"/api/friends/{one}/accept", headers={"X-CSRF-Token": csrf})


async def test_the_whole_night_flow(client, fake_idp, db_session, fake_tmdb_http, tmdb_key):
    await sign_in(client, fake_idp, "kai")
    await sign_in(client, fake_idp, "lou")
    await make_friends(client, fake_idp, "kai", "lou")

    # Kai hosts and invites Lou.
    csrf_k = await sign_in(client, fake_idp, "kai")
    made = await client.post(
        "/api/nights",
        json={"name": "Saturday", "invite": ["lou"], "survey_after_hours": 0},
        headers={"X-CSRF-Token": csrf_k},
    )
    assert made.status_code == 201
    night = made.json()
    night_id = night["id"]
    assert night["you_host"] is True
    assert {m["username"]: m["status"] for m in night["members"]} == {
        "kai": "accepted",
        "lou": "invited",
    }

    # Lou cannot touch the queue before accepting.
    csrf_l = await sign_in(client, fake_idp, "lou")
    too_soon = await client.post(
        f"/api/nights/{night_id}/queue",
        json={"type": "movie", "tmdb_id": 354912},
        headers={"X-CSRF-Token": csrf_l},
    )
    assert too_soon.status_code == 403

    accepted = await client.post(
        f"/api/nights/{night_id}/reply?coming=true", headers={"X-CSRF-Token": csrf_l}
    )
    assert accepted.status_code == 200
    assert accepted.json()["your_status"] == "accepted"

    # Both sides suggest into the same queue.
    lou_pick = await client.post(
        f"/api/nights/{night_id}/queue",
        json={"type": "movie", "tmdb_id": 354912},
        headers={"X-CSRF-Token": csrf_l},
    )
    assert [p["name"] for p in lou_pick.json()["queue"]] == ["Coco"]
    assert lou_pick.json()["queue"][0]["suggested_by"] == "lou"
    assert lou_pick.json()["queue"][0]["votes"] == 1

    csrf_k = await sign_in(client, fake_idp, "kai")
    kai_pick = await client.post(
        f"/api/nights/{night_id}/queue",
        json={"type": "movie", "tmdb_id": 550},
        headers={"X-CSRF-Token": csrf_k},
    )
    assert len(kai_pick.json()["queue"]) == 2

    # Kai votes for what Lou suggested, which puts it on top.
    voted = await client.post(
        f"/api/nights/{night_id}/vote",
        json={"type": "movie", "tmdb_id": 354912},
        headers={"X-CSRF-Token": csrf_k},
    )
    top = voted.json()["queue"][0]
    assert top["name"] == "Coco" and top["votes"] == 2 and top["you_voted"] is True

    # Voting again takes it back.
    unvoted = await client.post(
        f"/api/nights/{night_id}/vote",
        json={"type": "movie", "tmdb_id": 354912},
        headers={"X-CSRF-Token": csrf_k},
    )
    coco = next(p for p in unvoted.json()["queue"] if p["name"] == "Coco")
    assert coco["votes"] == 1 and coco["you_voted"] is False

    # The host settles it, and it lands in both histories at once.
    settled = await client.post(
        f"/api/nights/{night_id}/watched",
        json={"type": "movie", "tmdb_id": 354912},
        headers={"X-CSRF-Token": csrf_k},
    )
    assert settled.status_code == 200
    assert settled.json()["status"] == "watched"
    assert settled.json()["watched"]["name"] == "Coco"

    events = (
        await db_session.execute(
            select(WatchEvent, User.username).join(User, User.id == WatchEvent.user_id)
        )
    ).all()
    assert sorted(name for _, name in events) == ["kai", "lou"]
    assert all(event.source == "watch_night" for event, _ in events)

    # Only a participant can settle it, and only the host.
    csrf_l = await sign_in(client, fake_idp, "lou")
    not_host = await client.post(
        f"/api/nights/{night_id}/watched",
        json={"type": "movie", "tmdb_id": 550},
        headers={"X-CSRF-Token": csrf_l},
    )
    assert not_host.status_code == 403

    # With zero hours the survey is due immediately.
    mine = (await client.get("/api/nights")).json()[0]
    assert mine["awaiting_your_verdict"] is True

    said = await client.post(
        f"/api/nights/{night_id}/verdict",
        json={"rating_10": 9, "loved": True, "note": "better than expected"},
        headers={"X-CSRF-Token": csrf_l},
    )
    assert said.status_code == 200
    assert said.json()["awaiting_your_verdict"] is False

    # The verdict is not filed away separately: it rates their own history.
    lou = (await db_session.execute(select(User).where(User.username == "lou"))).scalar_one()
    event = (
        await db_session.execute(select(WatchEvent).where(WatchEvent.user_id == lou.id))
    ).scalar_one()
    await db_session.refresh(event)
    assert event.rating_10 == 9 and event.loved is True


async def test_a_night_you_are_not_in_looks_like_it_does_not_exist(client, fake_idp, db_session):
    await sign_in(client, fake_idp, "mia")
    csrf = await sign_in(client, fake_idp, "ned")
    made = await client.post(
        "/api/nights", json={"name": "Private"}, headers={"X-CSRF-Token": csrf}
    )
    night_id = made.json()["id"]

    await sign_in(client, fake_idp, "mia")
    # 404 rather than 403: an outsider learns nothing, not even that it is
    # there to be refused.
    assert (await client.get("/api/nights")).json() == []
    peek = await client.post(
        f"/api/nights/{night_id}/reply?coming=true",
        headers={"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]},
    )
    assert peek.status_code == 404


async def test_the_survey_waits_for_the_delay(
    client, fake_idp, db_session, fake_tmdb_http, tmdb_key
):
    from app.routers import nights as nights_router

    await sign_in(client, fake_idp, "ola")
    csrf = await sign_in(client, fake_idp, "ola")
    made = await client.post(
        "/api/nights",
        json={"name": "Later", "survey_after_hours": 12},
        headers={"X-CSRF-Token": csrf},
    )
    night_id = made.json()["id"]
    await client.post(
        f"/api/nights/{night_id}/watched",
        json={"type": "movie", "tmdb_id": 354912},
        headers={"X-CSRF-Token": csrf},
    )

    # Just watched: too early to ask.
    assert (await nights_router.ask_for_verdicts(db_session))["nights"] == 0
    asked = (
        (await db_session.execute(select(Notification).where(Notification.kind == "night_survey")))
        .scalars()
        .all()
    )
    assert asked == []

    # Wind the clock back past the delay.
    night = (
        await db_session.execute(select(WatchNight).where(WatchNight.name == "Later"))
    ).scalar_one()
    night.watched_at = datetime.now(UTC) - timedelta(hours=13)
    await db_session.commit()

    result = await nights_router.ask_for_verdicts(db_session)
    assert result == {"nights": 1, "asked": 1}

    # And it is asked once, not on every run.
    assert (await nights_router.ask_for_verdicts(db_session))["nights"] == 0


async def test_account_search_is_not_shadowed_by_the_catalog_people_route(
    client, fake_idp, db_session
):
    """/api/people/{id} means a person in the catalog. Account search lives
    somewhere else, or the integer path parameter eats it."""
    await sign_in(client, fake_idp, "zed")
    await sign_in(client, fake_idp, "zoe")
    found = await client.get("/api/users/search?q=zed")
    assert found.status_code == 200
    assert [p["username"] for p in found.json()] == ["zed"]

    # Two characters minimum, so one keystroke does not scan everyone.
    assert (await client.get("/api/users/search?q=z")).json() == []


async def test_a_rewatched_favourite_appears_once(client, fake_idp, db_session):
    """Two loved watches of the same title are one favourite: the profile
    grid shows titles, not events, so a rewatch must not double a poster."""
    csrf = await sign_in(client, fake_idp, "ivy")
    await client.put("/api/me", json={"handle": "ivy"}, headers={"X-CSRF-Token": csrf})
    await seed_title(db_session, 37854, "One Piece")

    for _ in range(2):
        posted = await client.post(
            "/api/history",
            json={"type": "movie", "tmdb_id": 37854, "rating_10": 10, "loved": True},
            headers={"X-CSRF-Token": csrf},
        )
        assert posted.status_code in (200, 201)

    profile = (await client.get("/api/profiles/ivy")).json()
    names = [t["name"] for t in profile["favourites"]]
    assert names.count("One Piece") == 1


async def test_unfriending_works_both_ways(client, fake_idp, db_session):
    """Remove works on every state: an accepted friendship, an outgoing
    request (cancel), and an incoming one (decline)."""
    await sign_in(client, fake_idp, "jo")
    csrf_k = await sign_in(client, fake_idp, "kim")
    await client.post(
        "/api/friends/request", json={"username": "jo"}, headers={"X-CSRF-Token": csrf_k}
    )
    csrf_j = await sign_in(client, fake_idp, "jo")
    await client.post("/api/friends/kim/accept", headers={"X-CSRF-Token": csrf_j})

    # Unfriend after acceptance.
    gone = await client.delete("/api/friends/kim", headers={"X-CSRF-Token": csrf_j})
    assert gone.status_code == 204
    assert (await client.get("/api/friends")).json()["friends"] == []

    # Cancel an outgoing request.
    await client.post(
        "/api/friends/request", json={"username": "kim"}, headers={"X-CSRF-Token": csrf_j}
    )
    cancelled = await client.delete("/api/friends/kim", headers={"X-CSRF-Token": csrf_j})
    assert cancelled.status_code == 204
    assert (await client.get("/api/friends")).json()["outgoing"] == []

    # Decline an incoming request.
    csrf_k = await sign_in(client, fake_idp, "kim")
    await client.post(
        "/api/friends/request", json={"username": "jo"}, headers={"X-CSRF-Token": csrf_k}
    )
    csrf_j = await sign_in(client, fake_idp, "jo")
    declined = await client.delete("/api/friends/kim", headers={"X-CSRF-Token": csrf_j})
    assert declined.status_code == 204
    assert (await client.get("/api/friends")).json()["incoming"] == []
