import uuid

from sqlalchemy import Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin


class AuthSettings(Base, CreatedAtMixin):
    """Which sign-in methods are live. One row per tenant, editable by an
    admin at runtime; the API refuses to leave both methods disabled."""

    __tablename__ = "auth_settings"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    oidc_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    password_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # When on, an unknown person can create their own password account.
    # Off by default: this is a private install.
    registration_open: Mapped[bool] = mapped_column(Boolean, default=False)
