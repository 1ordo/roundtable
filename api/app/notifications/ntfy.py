"""ntfy push delivery. Failures are logged and swallowed: push is a bonus,
the in-app inbox is the source of truth."""

import logging

import httpx

from app.config import get_settings
from app.models import User

logger = logging.getLogger("roundtable.ntfy")


def topic_for(user: User) -> str:
    return f"{get_settings().ntfy_topic_prefix}{user.username.lower()}"


async def push(user: User, title: str, message: str) -> bool:
    settings = get_settings()
    if not settings.ntfy_url:
        return False
    url = f"{settings.ntfy_url.rstrip('/')}/{topic_for(user)}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, content=message.encode(), headers={"Title": title})
        return resp.status_code < 300
    except httpx.HTTPError:
        logger.warning("ntfy push failed for %s", user.username)
        return False
