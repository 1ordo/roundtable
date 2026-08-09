"""Pocket ID OIDC client: authorization code flow with PKCE.

Kept behind a small class so tests can substitute a fake and so an
email+passkey provider can be added later without touching the routes.
"""

import base64
import hashlib
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from app.config import get_settings

DISCOVERY_TTL = 3600


class OIDCError(Exception):
    pass


def make_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


class OIDCProvider:
    def __init__(self) -> None:
        self._discovery: dict[str, Any] | None = None
        self._discovery_at: float = 0.0
        self._jwk_client: jwt.PyJWKClient | None = None

    async def discovery(self) -> dict[str, Any]:
        now = time.monotonic()
        if self._discovery is None or now - self._discovery_at > DISCOVERY_TTL:
            url = f"{get_settings().oidc_issuer.rstrip('/')}/.well-known/openid-configuration"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                resp.raise_for_status()
            self._discovery = resp.json()
            self._discovery_at = now
            self._jwk_client = jwt.PyJWKClient(self._discovery["jwks_uri"])
        return self._discovery

    async def authorize_url(self, state: str, nonce: str, code_challenge: str) -> str:
        settings = get_settings()
        disco = await self.discovery()
        params = {
            "response_type": "code",
            "client_id": settings.oidc_client_id,
            "redirect_uri": settings.oidc_redirect_uri,
            "scope": "openid profile email",
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{disco['authorization_endpoint']}?{urlencode(params)}"

    async def exchange_code(self, code: str, code_verifier: str) -> dict[str, Any]:
        settings = get_settings()
        disco = await self.discovery()
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.oidc_redirect_uri,
            "client_id": settings.oidc_client_id,
            "client_secret": settings.oidc_client_secret,
            "code_verifier": code_verifier,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(disco["token_endpoint"], data=data)
        if resp.status_code != 200:
            raise OIDCError(f"token endpoint returned {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    async def verify_id_token(self, id_token: str, nonce: str) -> dict[str, Any]:
        settings = get_settings()
        await self.discovery()
        assert self._jwk_client is not None
        signing_key = self._jwk_client.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=settings.oidc_client_id,
            issuer=get_settings().oidc_issuer.rstrip("/"),
        )
        if claims.get("nonce") != nonce:
            raise OIDCError("nonce mismatch")
        return claims


provider = OIDCProvider()
