"""Audit log plumbing. One helper, called from anywhere that matters.

Writes ride the caller's transaction: if the action rolls back, so does its
audit row, which keeps the log truthful."""

from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else None


async def audit(
    db: AsyncSession,
    action: str,
    *,
    actor: User | None = None,
    request: Request | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            tenant_id=actor.tenant_id if actor else None,
            actor_user_id=actor.id if actor else None,
            action=action,
            object_type=object_type,
            object_id=object_id,
            ip=_client_ip(request),
            user_agent=(request.headers.get("user-agent", "")[:400] or None) if request else None,
            detail=detail,
        )
    )
    await db.flush()
