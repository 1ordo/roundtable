"""What a subscription earned this month, for people who asked to know."""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.db import get_db
from app.models import User
from app.tracking import expenses

router = APIRouter(prefix="/api")


@router.get("/services/idle")
async def my_idle_services(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Subscribed services with a silent month behind them.

    Empty unless the person switched the reminders on: the app never
    volunteers opinions about money.
    """
    if not expenses.enabled(user):
        return {"enabled": False, "services": []}
    return {"enabled": True, "services": await expenses.idle_services(db, user)}
