"""Short-lived signed cookie carrying state, nonce, and PKCE verifier between
/auth/login and /auth/callback. Stateless, so no cleanup job is needed."""

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import get_settings

PREAUTH_COOKIE = "wd_preauth"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="watchpile-preauth")


def dump_preauth(payload: dict) -> str:
    return _serializer().dumps(payload)


def load_preauth(value: str) -> dict | None:
    try:
        return _serializer().loads(value, max_age=get_settings().preauth_ttl_seconds)
    except (BadSignature, SignatureExpired):
        return None
