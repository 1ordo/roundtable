import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin


class Tenant(Base, CreatedAtMixin):
    """Single row today. Exists so every table is tenant-scoped from day one,
    which is the cheapest possible SaaS insurance."""

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), default="default")


class User(Base, CreatedAtMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    oidc_subject: Mapped[str | None] = mapped_column(String(255), unique=True)
    username: Mapped[str] = mapped_column(String(120), unique=True)
    # The name other people see and search for. Chosen by the person rather
    # than inherited from the identity provider, lowercase, and unique.
    # Null until they pick one, at which point the username stops being
    # shown anywhere public.
    handle: Mapped[str | None] = mapped_column(String(30), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(60))
    # Argon2 hash. Null means this account has no password and can only
    # sign in through the identity provider.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    role: Mapped[str] = mapped_column(String(16), default="member")  # admin | member
    avatar_path: Mapped[str | None] = mapped_column(String(255))
    # The one line they chose to put at the top of their profile. On the user
    # rather than as a flag on the quote, so "one each" is the schema saying
    # it rather than a rule the code has to keep remembering.
    featured_quote_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("quotes.id", ondelete="SET NULL")
    )
    country_code: Mapped[str | None] = mapped_column(String(2))
    # Streaming services the user subscribes to, as TMDB provider ids.
    services: Mapped[list] = mapped_column(JSONB, default=list)
    # Onboarding preferences: {"languages": ["ar", "en"], "genres": [28, 35]}
    prefs: Mapped[dict] = mapped_column(JSONB, default=dict)
    api_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Who can see this person's lists, history, stats and comments:
    #   public   anyone signed in to this instance
    #   friends  accepted friends only
    #   private  nobody but them
    # Nothing is ever visible to the open internet at any setting.
    visibility: Mapped[str] = mapped_column(String(8), default="friends")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sessions: Mapped[list["Session"]] = relationship(back_populates="user")


class Session(Base, CreatedAtMixin):
    """Server-side sessions. The cookie holds a random token; only its SHA-256
    lands in the database, so a DB leak does not leak usable cookies."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))

    user: Mapped[User] = relationship(back_populates="sessions")
