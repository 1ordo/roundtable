"""A ceiling on how much of the operator's money one account can spend.

Every other rate limit in the app protects the instance. This one protects
the person paying for it: the assistant calls a paid endpoint, and without a
ceiling one signed-in account can loop it for as many tokens as the provider
will sell. On a household instance that is a surprise; on anything with open
registration it is the bill.

Fails open when Redis cannot be reached, like the token limiter, and says so
in the log. Refusing instead would make Redis a single point of failure for
the assistant, and spending money uncounted needs both an abusive account
and a broken Redis at the same moment. An operator in that position has a
louder problem than their token bill.
"""

import logging
from datetime import UTC, datetime

from fastapi import HTTPException

from app.config import get_settings
from app.models import User

logger = logging.getLogger("roundtable.ai")

# Per person, per hour, across chat, ask-search and explain together. Enough
# for a real conversation and a long way short of a loop.
PER_HOUR = 40


async def spend(user: User, cost: int = 1) -> None:
    """Count one assistant call against this hour, or refuse."""
    settings = get_settings()
    try:
        from redis.asyncio import Redis

        redis = Redis.from_url(settings.redis_url)
        try:
            key = f"ai:{user.id}:{datetime.now(UTC).strftime('%Y%m%d%H')}"
            used = await redis.incrby(key, cost)
            # Two hours, so the window cannot be reset by a well-timed gap.
            await redis.expire(key, 7200)
        finally:
            await redis.aclose()
    except Exception:
        logger.warning("ai budget counter unavailable, letting the request through uncounted")
        return

    if used > PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail=f"that is {PER_HOUR} questions this hour. Try again shortly.",
        )
