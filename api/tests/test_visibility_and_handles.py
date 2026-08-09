"""Privacy levels and self-chosen handles.

The visibility tests matter more than most: a setting that holds on one
endpoint and leaks on another is worse than no setting, so these check the
shared helper that every endpoint is supposed to go through."""

import pytest

from app.models import Friendship, User
from app.social import handles, visibility
from tests.util import do_login


async def make(db, username: str, level: str = "friends") -> User:
    """A second person, without going through the login dance."""
    from sqlalchemy import select

    from app.models import Tenant

    tenant = (await db.execute(select(Tenant))).scalars().first()
    user = User(
        tenant_id=tenant.id,
        username=username,
        email=f"{username}@test",
        visibility=level,
        prefs={},
    )
    db.add(user)
    await db.flush()
    return user


async def befriend(db, a: User, b: User) -> None:
    db.add(Friendship(requester_id=a.id, addressee_id=b.id, status="accepted"))
    await db.flush()


class TestVisibility:
    async def test_private_hides_from_everyone_including_friends(
        self, client, fake_idp, db_session
    ):
        await do_login(client, fake_idp, {"sub": "s1", "preferred_username": "viewer"})
        from sqlalchemy import select

        viewer = (
            await db_session.execute(select(User).where(User.username == "viewer"))
        ).scalar_one()
        hermit = await make(db_session, "hermit", "private")
        await befriend(db_session, viewer, hermit)
        await db_session.commit()

        assert await visibility.can_see(db_session, viewer, hermit) is False
        assert hermit.id not in await visibility.visible_user_ids(db_session, viewer)

    async def test_private_still_sees_their_own_things(self, client, fake_idp, db_session):
        from sqlalchemy import select

        await do_login(client, fake_idp, {"sub": "s2", "preferred_username": "solo"})
        solo = (await db_session.execute(select(User).where(User.username == "solo"))).scalar_one()
        solo.visibility = "private"
        await db_session.commit()

        assert await visibility.can_see(db_session, solo, solo) is True
        assert solo.id in await visibility.visible_user_ids(db_session, solo)

    async def test_friends_level_needs_an_accepted_friendship(self, client, fake_idp, db_session):
        from sqlalchemy import select

        await do_login(client, fake_idp, {"sub": "s3", "preferred_username": "watcher"})
        watcher = (
            await db_session.execute(select(User).where(User.username == "watcher"))
        ).scalar_one()
        friend = await make(db_session, "pal", "friends")
        stranger = await make(db_session, "stranger", "friends")
        await db_session.commit()

        assert await visibility.can_see(db_session, watcher, friend) is False
        await befriend(db_session, friend, watcher)
        await db_session.commit()
        # Direction must not matter: they asked, not us.
        assert await visibility.can_see(db_session, watcher, friend) is True
        assert await visibility.can_see(db_session, watcher, stranger) is False

    async def test_a_pending_request_is_not_a_friendship(self, client, fake_idp, db_session):
        from sqlalchemy import select

        await do_login(client, fake_idp, {"sub": "s4", "preferred_username": "hopeful"})
        hopeful = (
            await db_session.execute(select(User).where(User.username == "hopeful"))
        ).scalar_one()
        target = await make(db_session, "target", "friends")
        db_session.add(
            Friendship(requester_id=hopeful.id, addressee_id=target.id, status="pending")
        )
        await db_session.commit()

        assert await visibility.can_see(db_session, hopeful, target) is False

    async def test_public_is_visible_to_any_signed_in_person_but_not_to_nobody(
        self, client, fake_idp, db_session
    ):
        from sqlalchemy import select

        await do_login(client, fake_idp, {"sub": "s5", "preferred_username": "reader"})
        reader = (
            await db_session.execute(select(User).where(User.username == "reader"))
        ).scalar_one()
        loud = await make(db_session, "loud", "public")
        await db_session.commit()

        assert await visibility.can_see(db_session, reader, loud) is True
        # Signed out sees nothing, whatever the setting says.
        assert await visibility.can_see(db_session, None, loud) is False

    async def test_inactive_public_accounts_drop_out_of_the_visible_set(
        self, client, fake_idp, db_session
    ):
        from sqlalchemy import select

        await do_login(client, fake_idp, {"sub": "s6", "preferred_username": "seeker"})
        seeker = (
            await db_session.execute(select(User).where(User.username == "seeker"))
        ).scalar_one()
        gone = await make(db_session, "gone", "public")
        gone.is_active = False
        await db_session.commit()

        assert gone.id not in await visibility.visible_user_ids(db_session, seeker)


class TestHandles:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Lordo", "lordo"),
            ("  @Nadia  ", "nadia"),
            ("film_buff_99", "film_buff_99"),
        ],
    )
    def test_accepts_and_normalises(self, raw, expected):
        assert handles.clean(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "ab",  # too short
            "x" * 25,  # too long
            "has space",
            "has-dash",
            "has.dot",
            "_leading",
            "trailing_",
            "double__under",
            "9starts_with_digit",
            "admin",
            "Watchpile",
            "emoji_face",  # placeholder, replaced below
        ],
    )
    def test_rejects_with_a_reason(self, raw):
        if raw == "emoji_face":
            raw = "lordoе"  # Cyrillic e, looks identical to Latin e
        with pytest.raises(handles.HandleError) as caught:
            handles.clean(raw)
        assert str(caught.value), "every rejection needs a reason worth showing"

    def test_lookalike_characters_are_refused(self):
        """Without this, someone registers a handle that renders identically
        to another person's and impersonates them."""
        with pytest.raises(handles.HandleError):
            handles.clean("lоrdo")  # Cyrillic o

    async def test_a_taken_handle_cannot_be_claimed_twice(self, client, fake_idp, db_session):
        from sqlalchemy import select

        await do_login(client, fake_idp, {"sub": "s7", "preferred_username": "first"})
        first = (
            await db_session.execute(select(User).where(User.username == "first"))
        ).scalar_one()
        await handles.claim(db_session, first, "the_good_one")
        await db_session.commit()

        second = await make(db_session, "second")
        with pytest.raises(handles.HandleError):
            await handles.claim(db_session, second, "The_Good_One")

    async def test_keeping_your_own_handle_is_not_a_collision(self, client, fake_idp, db_session):
        from sqlalchemy import select

        await do_login(client, fake_idp, {"sub": "s8", "preferred_username": "steady"})
        user = (
            await db_session.execute(select(User).where(User.username == "steady"))
        ).scalar_one()
        await handles.claim(db_session, user, "steady_hand")
        await db_session.commit()
        # Saving the profile again with the same handle must not fail.
        assert await handles.claim(db_session, user, "steady_hand") == "steady_hand"
