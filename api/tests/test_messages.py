"""Direct messages, and the one rule that matters: friends only.

An app where anyone can message anyone needs blocking and moderation. This
one does not have those, so accepting a friend request is the consent, and
these tests are what keep that true."""

from sqlalchemy import select

from app.models import DirectMessage, Friendship, User
from tests.util import do_login


async def make(db, username: str, handle: str) -> User:
    from app.models import Tenant

    tenant = (await db.execute(select(Tenant))).scalars().first()
    user = User(
        tenant_id=tenant.id,
        username=username,
        handle=handle,
        email=f"{username}@test",
        visibility="friends",
        prefs={},
    )
    db.add(user)
    await db.flush()
    return user


async def sign_in(client, fake_idp, db, username: str, handle: str) -> tuple[dict, User]:
    await do_login(client, fake_idp, {"sub": username, "preferred_username": username})
    user = (await db.execute(select(User).where(User.username == username))).scalar_one()
    user.handle = handle
    await db.commit()
    headers = {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}
    return headers, user


async def test_a_stranger_cannot_be_messaged(client, fake_idp, db_session):
    headers, _ = await sign_in(client, fake_idp, db_session, "writer", "writer")
    await make(db_session, "stranger", "stranger")
    await db_session.commit()

    sent = await client.post("/api/messages/stranger", json={"body": "hi"}, headers=headers)
    assert sent.status_code == 404
    assert (await db_session.execute(select(DirectMessage))).scalars().first() is None


async def test_a_pending_request_is_not_enough(client, fake_idp, db_session):
    headers, me = await sign_in(client, fake_idp, db_session, "eager", "eager")
    them = await make(db_session, "target", "target")
    db_session.add(Friendship(requester_id=me.id, addressee_id=them.id, status="pending"))
    await db_session.commit()

    sent = await client.post("/api/messages/target", json={"body": "hi"}, headers=headers)
    assert sent.status_code == 404


async def test_friends_can_write_to_each_other(client, fake_idp, db_session):
    headers, me = await sign_in(client, fake_idp, db_session, "one", "one_handle")
    them = await make(db_session, "two", "two_handle")
    db_session.add(Friendship(requester_id=them.id, addressee_id=me.id, status="accepted"))
    await db_session.commit()

    sent = await client.post(
        "/api/messages/two_handle", json={"body": "seen anything good?"}, headers=headers
    )
    assert sent.status_code == 201
    assert sent.json()["mine"] is True

    thread = await client.get("/api/messages/two_handle")
    assert [m["body"] for m in thread.json()["messages"]] == ["seen anything good?"]
    assert thread.json()["person"]["handle"] == "two_handle"


async def test_you_cannot_message_yourself(client, fake_idp, db_session):
    headers, _ = await sign_in(client, fake_idp, db_session, "solo", "solo_handle")
    sent = await client.post("/api/messages/solo_handle", json={"body": "hi"}, headers=headers)
    assert sent.status_code == 404


async def test_opening_a_thread_marks_their_messages_read(client, fake_idp, db_session):
    headers, me = await sign_in(client, fake_idp, db_session, "reader", "reader_h")
    them = await make(db_session, "sender", "sender_h")
    db_session.add(Friendship(requester_id=me.id, addressee_id=them.id, status="accepted"))
    db_session.add(DirectMessage(sender_id=them.id, recipient_id=me.id, body="ping"))
    await db_session.commit()

    before = await client.get("/api/messages-unread")
    assert before.json()["unread"] == 1

    await client.get("/api/messages/sender_h")
    after = await client.get("/api/messages-unread")
    assert after.json()["unread"] == 0

    # Your own unread count is only about what they sent you.
    await client.post("/api/messages/sender_h", json={"body": "pong"}, headers=headers)
    assert (await client.get("/api/messages-unread")).json()["unread"] == 0


async def test_conversations_list_one_row_per_person(client, fake_idp, db_session):
    headers, me = await sign_in(client, fake_idp, db_session, "hub", "hub_h")
    a = await make(db_session, "alpha", "alpha_h")
    b = await make(db_session, "beta", "beta_h")
    for other in (a, b):
        db_session.add(Friendship(requester_id=me.id, addressee_id=other.id, status="accepted"))
    await db_session.commit()

    await client.post("/api/messages/alpha_h", json={"body": "first"}, headers=headers)
    await client.post("/api/messages/alpha_h", json={"body": "second"}, headers=headers)
    await client.post("/api/messages/beta_h", json={"body": "hello"}, headers=headers)

    rows = (await client.get("/api/messages")).json()
    assert len(rows) == 2, "one row per person, not per message"
    by_handle = {r["person"]["handle"]: r for r in rows}
    assert by_handle["alpha_h"]["last"] == "second", "the newest message is the preview"
    assert all(r["from_them"] is False for r in rows)


async def test_a_message_raises_an_inbox_row_for_the_recipient(client, fake_idp, db_session):
    from app.models import Notification

    headers, me = await sign_in(client, fake_idp, db_session, "poster", "poster_h")
    them = await make(db_session, "getter", "getter_h")
    db_session.add(Friendship(requester_id=me.id, addressee_id=them.id, status="accepted"))
    await db_session.commit()

    await client.post("/api/messages/getter_h", json={"body": "look at this"}, headers=headers)
    rows = (
        (await db_session.execute(select(Notification).where(Notification.user_id == them.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].kind == "message"
    assert "look at this" in rows[0].message
