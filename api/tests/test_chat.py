"""The assistant may describe, but the catalog decides what exists."""

import pytest

from app.ai import chat
from app.models import Title
from tests.test_offline_catalog import OMDB_INCEPTION, OMDB_PARASITE, _build_catalog
from tests.util import LORDO, do_login


def _fake(name: str, **kw) -> Title:
    return Title(
        tmdb_id=kw.get("tmdb_id", 1),
        type="movie",
        name=name,
        **{k: v for k, v in kw.items() if k != "tmdb_id"},
    )


def test_reply_is_house_style():
    assert chat._tidy("Tense — and smart") == "Tense, and smart"
    assert chat._tidy("Tense – and smart") == "Tense, and smart"
    assert "—" not in chat._tidy("a—b")


async def test_chat_only_returns_real_catalog_titles(
    client, fake_idp, db_session, ai_enabled, monkeypatch
):
    """The agent can discuss anything; it can only SHOW what exists."""
    await _build_catalog(db_session)
    from sqlalchemy import select

    from app.ai import agent
    from app.ai import client as ai_client

    inception = (
        await db_session.execute(select(Title).where(Title.name == "Inception"))
    ).scalar_one()
    await db_session.commit()

    async def scripted(db, messages, tools, max_tokens=1200, tool_choice=None):
        # The model answers directly, naming one real title (confirmed by
        # id) and one that does not exist anywhere.
        import json

        return {
            "content": json.dumps(
                {
                    "reply": "Try Inception, and also The Invented Film.",
                    "titles": [
                        {
                            "name": "Inception",
                            "year": 2010,
                            "tmdb_id": inception.tmdb_id,
                            "type": "movie",
                        },
                        {
                            "name": "The Invented Film",
                            "year": None,
                            "tmdb_id": None,
                            "type": "movie",
                        },
                    ],
                    "list_name": None,
                }
            )
        }

    monkeypatch.setattr(ai_client, "chat_tools", scripted)
    monkeypatch.setattr(agent.client, "chat_tools", scripted)

    await do_login(client, fake_idp, LORDO)
    headers = {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}
    resp = await client.post("/api/chat", json={"message": "something clever"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    names = [r["name"] for r in body["results"]]
    assert names == ["Inception"], "the invented title is dropped"
    assert "Inception" in body["reply"]
    assert "could not be verified" in body["reply"], "the drop is said, not hidden"


async def test_chat_requires_ai(client, fake_idp, db_session):
    await do_login(client, fake_idp, LORDO)
    headers = {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}
    resp = await client.post("/api/chat", json={"message": "hi"}, headers=headers)
    assert resp.status_code == 503
    assert resp.json()["detail"] == "ai_disabled"


async def test_chat_needs_csrf(client, fake_idp):
    await do_login(client, fake_idp, LORDO)
    resp = await client.post("/api/chat", json={"message": "hi"})
    assert resp.status_code == 403


async def test_profile_block_describes_the_person(client, fake_idp, db_session):
    from sqlalchemy import select

    from app.models import Interaction, User

    await _build_catalog(db_session)
    await do_login(client, fake_idp, LORDO)
    user = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
    user.country_code = "EG"
    user.prefs = {"languages": ["ar", "en"]}
    parasite = (
        await db_session.execute(select(Title).where(Title.imdb_id == "tt6751668"))
    ).scalar_one()
    db_session.add(Interaction(user_id=user.id, title_id=parasite.id, kind="like"))
    await db_session.commit()

    block = await chat._profile_block(db_session, user)
    assert "EG" in block
    assert "ar" in block
    assert "Parasite" in block


@pytest.mark.parametrize("payload", [OMDB_INCEPTION, OMDB_PARASITE])
def test_fixtures_are_shaped_like_omdb(payload):
    assert payload["Response"] == "True"
    assert payload["imdbID"].startswith("tt")


async def test_an_ungrounded_answer_is_honest_rather_than_padded(
    client, fake_idp, db_session, ai_enabled, monkeypatch
):
    """The old design padded a vague reply with the top of the taste
    ranking, which is how a question about The Nun was answered with
    Batman & Robin. An answer with no grounds now says so and shows
    nothing, instead of dressing the ranking up as a result."""
    await _build_catalog(db_session)
    from app.ai import agent
    from app.ai import client as ai_client

    async def vague(db, messages, tools, max_tokens=1200, tool_choice=None):
        import json

        return {
            "content": json.dumps(
                {
                    "reply": "I could not verify which films are connected to that one.",
                    "titles": [],
                    "list_name": None,
                }
            )
        }

    monkeypatch.setattr(ai_client, "chat_tools", vague)
    monkeypatch.setattr(agent.client, "chat_tools", vague)

    await do_login(client, fake_idp, LORDO)
    headers = {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}
    body = (
        await client.post(
            "/api/chat", json={"message": "everything related to the nun"}, headers=headers
        )
    ).json()

    assert body["results"] == [], "no picks are invented to fill the silence"
    assert "could not verify" in body["reply"]


async def test_a_plain_answer_needs_no_titles(
    client, fake_idp, db_session, ai_enabled, monkeypatch
):
    from app.ai import agent
    from app.ai import client as ai_client

    await _build_catalog(db_session)

    async def plain(db, messages, tools, max_tokens=1200, tool_choice=None):
        import json

        return {
            "content": json.dumps(
                {
                    "reply": "Nothing in your catalog is a silent film.",
                    "titles": [],
                    "list_name": None,
                }
            )
        }

    monkeypatch.setattr(ai_client, "chat_tools", plain)
    monkeypatch.setattr(agent.client, "chat_tools", plain)

    await do_login(client, fake_idp, LORDO)
    headers = {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}
    body = (
        await client.post("/api/chat", json={"message": "any silent films?"}, headers=headers)
    ).json()
    assert body["results"] == []
    assert "silent" in body["reply"]
