"""Friends and watch nights.

A watch night here is a plan two or more people make together, not a list
one person owns. That shape drives the tables:

  friendship    a request that has to be accepted, so nobody is added to
                anything without agreeing to it.
  watch_nights  the plan itself, with a host and a status.
  night_members one row per invited person, each with their own answer, so
                "invited" and "coming" are different things.
  night_picks   the shared queue. Everyone who accepted can add to it, and
                every pick remembers who suggested it.
  night_verdicts what each person thought afterwards, asked once enough
                time has passed that they have actually seen it.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.catalog import Title
    from app.models.core import User

from app.models.base import Base, CreatedAtMixin


class Friendship(Base, CreatedAtMixin):
    """A friendship, from the moment it is asked for.

    One row per pair, held in the direction it was asked. Declining deletes
    the row rather than storing a refusal, so asking again later is a fresh
    request and not an argument with history."""

    __tablename__ = "friendships"
    __table_args__ = (UniqueConstraint("requester_id", "addressee_id", name="uq_friendship_pair"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    requester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    addressee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    # pending | accepted
    status: Mapped[str] = mapped_column(String(12), default="pending")
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WatchNight(Base, CreatedAtMixin):
    """A plan to watch something together."""

    __tablename__ = "watch_nights"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    host_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # planning | watched | cancelled
    status: Mapped[str] = mapped_column(String(12), default="planning")
    # What was actually watched, set when the night is marked done.
    watched_title_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("titles.id", ondelete="SET NULL")
    )
    watched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # How long to wait before asking what everyone thought. Long enough that
    # the film is finished and the evening is over, and it is adjustable
    # because "later" means different things to different people.
    survey_after_hours: Mapped[int] = mapped_column(Integer, default=12)
    surveyed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NightMember(Base, CreatedAtMixin):
    """One person's place in a night, and whether they said yes."""

    __tablename__ = "night_members"
    __table_args__ = (UniqueConstraint("night_id", "user_id", name="uq_night_member"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    night_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("watch_nights.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    # invited | accepted | declined
    status: Mapped[str] = mapped_column(String(12), default="invited")
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NightPick(Base, CreatedAtMixin):
    """A title in the shared queue, and who put it there."""

    __tablename__ = "night_picks"
    __table_args__ = (UniqueConstraint("night_id", "title_id", name="uq_night_pick"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    night_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("watch_nights.id", ondelete="CASCADE"), index=True
    )
    title_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("titles.id", ondelete="CASCADE"))
    suggested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # Everyone who accepted can vote a pick up. A list of user id strings,
    # so a vote can be taken back as easily as it was given.
    voter_ids: Mapped[list] = mapped_column(JSONB, default=list)


class NightVerdict(Base, CreatedAtMixin):
    """What one person thought, once they have had time to see it."""

    __tablename__ = "night_verdicts"
    __table_args__ = (UniqueConstraint("night_id", "user_id", name="uq_night_verdict"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    night_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("watch_nights.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    rating_10: Mapped[int | None] = mapped_column(Integer)
    loved: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text)


class FollowedPerson(Base, CreatedAtMixin):
    """An actor or director someone follows.

    The name and picture are copied in rather than looked up every time:
    a follow list has to render without a round trip per row, and a person
    who leaves the catalog should still show as followed."""

    __tablename__ = "followed_people"
    __table_args__ = (UniqueConstraint("user_id", "person_id", name="uq_followed_person"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    # TMDB person id.
    person_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(200))
    profile_path: Mapped[str | None] = mapped_column(String(200))
    # The most recent release already seen for them, so a new one can be
    # told apart from the back catalog.
    last_seen_credit: Mapped[int | None] = mapped_column(Integer)


class Comment(Base, CreatedAtMixin):
    """What someone thought, on the record.

    Visibility is not stored here: a comment is visible to exactly whoever
    can see its author's profile. Keeping one source of truth means changing
    your profile to private takes everything you have ever written with it,
    rather than leaving a trail of comments the setting does not cover."""

    __tablename__ = "comments"
    __table_args__ = (
        Index("ix_comments_title_created", "title_id", "created_at"),
        Index("ix_comments_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Nullable, because a post with nothing attached is still a post. A
    # comment is simply a post that names a title.
    title_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("titles.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[str] = mapped_column(String(2000))
    # Sharing someone else's post with your own opinion on top. Deleting the
    # original leaves the reshare standing with its own words, which is why
    # this is SET NULL rather than CASCADE.
    shared_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("comments.id", ondelete="SET NULL"), index=True
    )
    # A reply to another post. Deleting the parent takes its replies with
    # it, unlike a reshare, because a reply out of context is nonsense.
    reply_to_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), index=True
    )
    # Folded away until the reader asks, the same as the parents guide does.
    spoiler: Mapped[bool] = mapped_column(Boolean, default=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship()
    title: Mapped["Title"] = relationship()
    shared: Mapped["Comment | None"] = relationship(remote_side=[id], foreign_keys=[shared_id])
    reply_to: Mapped["Comment | None"] = relationship(remote_side=[id], foreign_keys=[reply_to_id])


class CommentLike(Base, CreatedAtMixin):
    __tablename__ = "comment_likes"
    __table_args__ = (UniqueConstraint("comment_id", "user_id", name="uq_comment_like"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    comment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )


class Quote(Base, CreatedAtMixin):
    """A line from a film, and who said it.

    Two sources, kept apart by `source`: lines pulled from the catalog, and
    lines someone typed in themselves. Both are attributed to a character
    where one is known, because a quote without a speaker is half a quote."""

    __tablename__ = "quotes"
    __table_args__ = (Index("ix_quotes_title_created", "title_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("titles.id", ondelete="CASCADE"), index=True
    )
    # Null for lines that came with the catalog rather than from a person.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[str] = mapped_column(String(600))
    character: Mapped[str | None] = mapped_column(String(120))
    # catalog | user
    source: Mapped[str] = mapped_column(String(10), default="user")

    user: Mapped["User | None"] = relationship()
    title: Mapped["Title"] = relationship()


class QuoteLike(Base, CreatedAtMixin):
    __tablename__ = "quote_likes"
    __table_args__ = (UniqueConstraint("quote_id", "user_id", name="uq_quote_like"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    quote_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quotes.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )


class DirectMessage(Base, CreatedAtMixin):
    """A message between two people.

    Only between friends: an app where anyone can message anyone needs
    blocking, reporting and moderation, and none of that is worth building
    for a household. Accepting a friend request is the consent.

    A title can be attached, because "have you seen this" is most of what
    anyone sends."""

    __tablename__ = "direct_messages"
    __table_args__ = (
        # The index the thread query actually uses: both people, newest first.
        Index("ix_dm_pair_created", "sender_id", "recipient_id", "created_at"),
        Index("ix_dm_inbox", "recipient_id", "read_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    sender_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[str] = mapped_column(String(2000))
    title_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("titles.id", ondelete="SET NULL"))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sender: Mapped["User"] = relationship(foreign_keys=[sender_id])
    recipient: Mapped["User"] = relationship(foreign_keys=[recipient_id])
    title: Mapped["Title | None"] = relationship()
