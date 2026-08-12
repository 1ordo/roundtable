"""The AI key must survive a rename of the project.

This is a regression test for a real outage. A project-wide rename rewrote
the literal "watchdeck-ai:" to "roundtable-ai:" inside the Fernet key
derivation. The salt is a cryptographic input, so the derived key changed,
the stored AI key stopped decrypting, the app sent a broken credential
upstream, and the provider answered 401.

Nothing caught it. Every test encrypts and decrypts inside one process, so
they all agreed with each other; only a database holding a value written
before the change could show the problem. These tests hold the salt itself
still, which is the only thing that would have caught it.
"""

import base64
import hashlib

from cryptography.fernet import Fernet

from app.ai import crypto
from app.config import get_settings


def _encrypt_with(salt: str, value: str) -> str:
    """Encrypt the way a given version of this app would have."""
    digest = hashlib.sha256(f"{salt}{get_settings().secret_key}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest)).encrypt(value.encode()).decode()


def test_the_current_salt_is_exactly_this():
    """A find-and-replace over the word "roundtable" would change this, and
    every instance in the world would stop being able to read its own key.
    If a rename is genuinely wanted, add the old value to LEGACY_SALTS in the
    same commit and change this line deliberately."""
    assert crypto.SALT == "roundtable-ai:"


def test_the_salt_the_project_used_before_is_still_accepted():
    assert "watchdeck-ai:" in crypto.LEGACY_SALTS


def test_a_round_trip_works():
    assert crypto.decrypt(crypto.encrypt("sk-example-key")) == "sk-example-key"


def test_a_key_written_under_the_old_salt_still_opens():
    """The outage, reproduced. Before the fix this returned None, the app
    sent no credential, and the provider answered 401."""
    old = _encrypt_with("watchdeck-ai:", "sk-written-before-the-rename")
    assert crypto.decrypt(old) == "sk-written-before-the-rename"


def test_an_old_key_is_flagged_for_reseal_and_a_current_one_is_not():
    old = _encrypt_with("watchdeck-ai:", "sk-old")
    current = crypto.encrypt("sk-new")
    assert crypto.needs_reseal(old) is True
    assert crypto.needs_reseal(current) is False


def test_resealing_produces_something_readable_under_the_current_salt():
    old = _encrypt_with("watchdeck-ai:", "sk-old")
    fresh = crypto.reseal(old)
    assert fresh is not None
    assert fresh != old
    assert crypto.needs_reseal(fresh) is False
    assert crypto.decrypt(fresh) == "sk-old"


def test_rubbish_is_none_rather_than_an_exception():
    assert crypto.decrypt("not encrypted at all") is None
    assert crypto.reseal("not encrypted at all") is None
    assert crypto.needs_reseal("not encrypted at all") is False


async def test_reading_the_settings_reseals_an_old_key(db_session):
    """The self-heal: an operator should never learn any of this happened."""
    from app.ai import client
    from app.models import AISettings

    settings = await client.get_ai_settings(db_session)
    settings.api_key_enc = _encrypt_with("watchdeck-ai:", "sk-from-before")
    await db_session.commit()

    reloaded = await client.get_ai_settings(db_session)
    assert crypto.needs_reseal(reloaded.api_key_enc) is False, "should have been rewritten"
    assert crypto.decrypt(reloaded.api_key_enc) == "sk-from-before"

    # And it survives a fresh read from the database, not just in memory.
    await db_session.commit()
    from sqlalchemy import select

    row = (await db_session.execute(select(AISettings))).scalars().first()
    assert crypto.decrypt(row.api_key_enc) == "sk-from-before"
