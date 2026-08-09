"""The poster proxy: a URL builder pointing at another host, so it is
locked down rather than trusted."""

import pytest

from app.routers.profile import POSTER_SIZES
from tests.util import do_login


async def sign_in(client, fake_idp):
    await do_login(client, fake_idp, {"sub": "s-px", "preferred_username": "px"})


@pytest.mark.parametrize(
    "size,filename",
    [
        ("w185/../../etc", "passwd.jpg"),
        ("../../secret", "a.jpg"),
        ("w185", "../../../etc/passwd.jpg"),
        ("w185", "a/b.jpg"),
        ("w9999", "a.jpg"),
        ("w185", "script.js"),
        ("w185", "payload.html"),
        ("", "a.jpg"),
    ],
)
async def test_a_path_that_is_not_a_plain_image_is_refused(client, fake_idp, size, filename):
    await sign_in(client, fake_idp)
    response = await client.get(f"/api/media/tmdb/{size}/{filename}")
    assert response.status_code == 404, f"{size}/{filename} should not be fetched"


def test_the_size_list_is_closed():
    """The size goes straight into a URL on another host, so it comes from
    a fixed set rather than from the request."""
    assert "original" in POSTER_SIZES
    assert all(s == "original" or s.startswith("w") for s in POSTER_SIZES)
