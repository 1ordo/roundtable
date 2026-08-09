from urllib.parse import parse_qs, urlparse

from httpx import AsyncClient, Response


async def do_login(client: AsyncClient, fake_idp, claims: dict) -> Response:
    """Run the whole browser dance: /auth/login redirect, then the callback
    with the state the server issued."""
    fake_idp.claims = claims
    login_resp = await client.get("/auth/login")
    assert login_resp.status_code == 302
    state = parse_qs(urlparse(login_resp.headers["location"]).query)["state"][0]
    return await client.get(f"/auth/callback?code=fake-code&state={state}")


LORDO = {"sub": "sub-lordo", "preferred_username": "Lordo", "email": "admin@example.com"}
FRIEND = {"sub": "sub-nadia", "preferred_username": "Nadia", "email": "nadia@example.com"}
