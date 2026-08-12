"""At-rest encryption for the AI API key, derived from the app secret.

The salt below is part of the key derivation, so changing its text changes
the encryption key and orphans everything already stored. That happened
once: a project-wide rename rewrote the literal from "watchdeck-ai:" to
"roundtable-ai:", the stored key stopped decrypting, the app sent a broken
credential upstream, and the provider answered 401. Every test passed,
because a test encrypts and decrypts in the same process; only a database
with a key written before the change could show it.

Hence two things. The legacy salt is kept and tried on failure, so an
instance that predates the rename keeps working and re-seals itself on the
next save. And the salts are written out as literal strings that no
find-and-replace should ever touch again.
"""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

logger = logging.getLogger("roundtable.crypto")

# Do not rename these. They are cryptographic inputs, not branding.
SALT = "roundtable-ai:"
LEGACY_SALTS = ("watchdeck-ai:",)


def _fernet_for(salt: str) -> Fernet:
    digest = hashlib.sha256(f"{salt}{get_settings().secret_key}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str) -> str:
    return _fernet_for(SALT).encrypt(value.encode()).decode()


def decrypt(value: str) -> str | None:
    """Plaintext, or None when the value cannot be read at all.

    Tries the current salt, then every salt this app has ever used. A value
    that only opens under a legacy salt is readable but stale; needs_reseal
    reports that so the caller can write it back under the current one.
    """
    for salt in (SALT, *LEGACY_SALTS):
        try:
            return _fernet_for(salt).decrypt(value.encode()).decode()
        except (InvalidToken, ValueError):
            continue
    return None


def needs_reseal(value: str) -> bool:
    """Whether this ciphertext is readable but written under an old salt."""
    try:
        _fernet_for(SALT).decrypt(value.encode())
        return False
    except (InvalidToken, ValueError):
        pass
    for salt in LEGACY_SALTS:
        try:
            _fernet_for(salt).decrypt(value.encode())
            return True
        except (InvalidToken, ValueError):
            continue
    return False


def reseal(value: str) -> str | None:
    """Re-encrypt under the current salt, or None if it cannot be read."""
    plain = decrypt(value)
    return encrypt(plain) if plain is not None else None
