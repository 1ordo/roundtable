"""Email, through Resend.

Off until a key is set, and silent about it rather than noisy: an instance
with no email configured should behave exactly as it did before this
existed, not log a failure for every notification.

The address is only ever the one on the account. Nothing here takes a
recipient from a request, so no endpoint can be turned into a way to send
mail to an arbitrary address.
"""

import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import User

logger = logging.getLogger("watchpile.email")

ENDPOINT = "https://api.resend.com/emails"
TIMEOUT = 10.0


def configured() -> bool:
    settings = get_settings()
    return bool(getattr(settings, "resend_api_key", None))


def wants_email(user: User) -> bool:
    """Off by default. Email is more intrusive than an inbox row, so it is
    opted into rather than out of."""
    return bool((user.prefs or {}).get("email_alerts"))


def _html(title: str, message: str, link: str | None) -> str:
    """A plain, single column message. No tracking pixel, no images."""
    button = (
        f'<p style="margin:24px 0"><a href="{link}" '
        'style="background:#ec6a3f;color:#181114;padding:12px 20px;'
        'border-radius:8px;text-decoration:none;font-weight:600">Open Watchpile</a></p>'
        if link
        else ""
    )
    return (
        '<div style="font-family:system-ui,sans-serif;max-width:520px;margin:0 auto;'
        'padding:32px 24px;color:#1d2130">'
        f'<p style="font-size:12px;letter-spacing:2px;text-transform:uppercase;'
        f'color:#a2938e;margin:0">Watchpile</p>'
        f'<h1 style="font-size:22px;margin:12px 0 0">{title}</h1>'
        f'<p style="font-size:15px;line-height:1.6;margin:16px 0 0">{message}</p>'
        f"{button}"
        '<p style="font-size:12px;color:#a2938e;margin-top:32px">'
        "You can turn these off in Settings, Alerts.</p></div>"
    )


async def send(
    db: AsyncSession,
    user: User,
    subject: str,
    message: str,
    link: str | None = None,
) -> bool:
    """One email. Returns whether it actually went.

    Never raises: a notification that cannot be emailed is still in the
    inbox, and losing the inbox row because the mail failed would be the
    worse outcome."""
    if not configured() or not wants_email(user) or not user.email:
        return False

    settings = get_settings()
    payload = {
        "from": getattr(settings, "resend_from", None) or "Watchpile <onboarding@resend.dev>",
        "to": [user.email],
        "subject": subject,
        "html": _html(subject, message, link),
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as http:
            response = await http.post(
                ENDPOINT,
                json=payload,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            )
        if response.status_code >= 300:
            logger.warning("resend refused: %s %s", response.status_code, response.text[:200])
            return False
        return True
    except httpx.HTTPError as exc:
        logger.warning("could not reach resend: %s", exc)
        return False
