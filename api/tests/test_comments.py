"""Comments: visibility, signals, and the edit window."""

from app.ai import taste
from app.models import User
from tests.util import do_login


async def csrf(client) -> dict:
    return {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}


async def test_writing_a_comment_feeds_the_taste_vector(
    client, fake_idp, db_session, fake_tmdb_http, tmdb_key
):
    """The user asked for comments to count toward suggestions. A comment
    that does not create an interaction is decoration."""
    from sqlalchemy import select

    from app.models import Interaction

    await do_login(client, fake_idp, {"sub": "c1", "preferred_username": "writer"})
    headers = await csrf(client)

    response = await client.post(
        "/api/titles/movie/354912/comments",
        json={"body": "Held up better than I expected.", "spoiler": False},
        headers=headers,
    )
    assert response.status_code == 201

    user = (await db_session.execute(select(User).where(User.username == "writer"))).scalar_one()
    kinds = (
        (await db_session.execute(select(Interaction.kind).where(Interaction.user_id == user.id)))
        .scalars()
        .all()
    )
    assert "comment" in kinds
    # And the weight has to be registered, or the interaction is ignored.
    assert taste.INTERACTION_WEIGHTS.get("comment", 0) > 0


async def test_a_comment_is_only_visible_to_people_who_can_see_its_author(
    client, fake_idp, db_session, fake_tmdb_http, tmdb_key
):
    from sqlalchemy import select

    await do_login(client, fake_idp, {"sub": "c2", "preferred_username": "quiet"})
    headers = await csrf(client)
    await client.post(
        "/api/titles/movie/354912/comments",
        json={"body": "Only my friends should read this.", "spoiler": False},
        headers=headers,
    )
    # Default is friends only, and a stranger is not a friend.
    quiet = (await db_session.execute(select(User).where(User.username == "quiet"))).scalar_one()
    assert quiet.visibility == "friends"

    await do_login(client, fake_idp, {"sub": "c3", "preferred_username": "stranger"})
    seen = await client.get("/api/titles/movie/354912/comments")
    assert seen.status_code == 200
    assert seen.json()["total"] == 0, "a stranger must not see a friends-only comment"


async def test_you_cannot_edit_or_delete_someone_elses_comment(
    client, fake_idp, fake_tmdb_http, tmdb_key
):
    await do_login(client, fake_idp, {"sub": "c4", "preferred_username": "author"})
    headers = await csrf(client)
    made = await client.post(
        "/api/titles/movie/354912/comments",
        json={"body": "Mine.", "spoiler": False},
        headers=headers,
    )
    comment_id = made.json()["id"]

    await do_login(client, fake_idp, {"sub": "c5", "preferred_username": "meddler"})
    other = await csrf(client)
    edited = await client.patch(
        f"/api/comments/{comment_id}", json={"body": "Not mine.", "spoiler": False}, headers=other
    )
    # 404 rather than 403: whether it exists is not theirs to learn.
    assert edited.status_code == 404
    removed = await client.delete(f"/api/comments/{comment_id}", headers=other)
    assert removed.status_code == 404


async def test_a_quick_typo_fix_is_not_marked_as_edited(client, fake_idp, fake_tmdb_http, tmdb_key):
    await do_login(client, fake_idp, {"sub": "c6", "preferred_username": "typo"})
    headers = await csrf(client)
    made = await client.post(
        "/api/titles/movie/354912/comments",
        json={"body": "Teh best one.", "spoiler": False},
        headers=headers,
    )
    fixed = await client.patch(
        f"/api/comments/{made.json()['id']}",
        json={"body": "The best one.", "spoiler": False},
        headers=headers,
    )
    assert fixed.status_code == 200
    assert fixed.json()["edited_at"] is None, "a fix within the grace window is not an edit"
    assert fixed.json()["body"] == "The best one."


async def test_liking_is_a_toggle(client, fake_idp, fake_tmdb_http, tmdb_key):
    await do_login(client, fake_idp, {"sub": "c7", "preferred_username": "liker"})
    headers = await csrf(client)
    made = await client.post(
        "/api/titles/movie/354912/comments",
        json={"body": "Worth it.", "spoiler": False},
        headers=headers,
    )
    cid = made.json()["id"]

    on = await client.post(f"/api/comments/{cid}/like", headers=headers)
    assert on.json()["likes"] == 1 and on.json()["you_liked"] is True
    off = await client.post(f"/api/comments/{cid}/like", headers=headers)
    assert off.json()["likes"] == 0 and off.json()["you_liked"] is False
