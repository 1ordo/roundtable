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


def test_named_titles_use_whole_words():
    """A short title must not match inside another word."""
    candidates = [_fake("Her"), _fake("The Attack"), _fake("Paradise Now")]
    prose = "There are other options; The Attack and Paradise Now stand out."
    found = [t.name for t in chat._titles_named_in(prose, candidates)]
    assert found == ["The Attack", "Paradise Now"], "'Her' is not inside 'There' or 'other'"

    assert [t.name for t in chat._titles_named_in("Try Her tonight.", candidates)] == ["Her"]


def test_named_titles_keep_reply_order():
    candidates = [_fake("Parasite"), _fake("Inception")]
    found = [t.name for t in chat._titles_named_in("First Inception, then Parasite.", candidates)]
    assert found == ["Inception", "Parasite"]


def test_reply_is_house_style():
    assert chat._tidy("Tense — and smart") == "Tense, and smart"
    assert chat._tidy("Tense – and smart") == "Tense, and smart"
    assert "—" not in chat._tidy("a—b")


async def test_chat_only_returns_real_catalog_titles(
    client, fake_idp, db_session, ai_enabled, monkeypatch
):
    await _build_catalog(db_session)
    from app.ai import embeddings

    await embeddings.embed_missing_titles(db_session)
    await db_session.commit()

    async def fake_chat_json(db, system, user, max_tokens=800):
        # The model names one real title and one that does not exist.
        return {
            "reply": "Try Inception, and also The Invented Film.",
            "titles": ["Inception", "The Invented Film"],
        }

    monkeypatch.setattr(chat.client, "chat_json", fake_chat_json)

    await do_login(client, fake_idp, LORDO)
    headers = {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}
    resp = await client.post("/api/chat", json={"message": "something clever"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    names = [r["name"] for r in body["results"]]
    assert names == ["Inception"], "the invented title is dropped"
    assert "Inception" in body["reply"]


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


async def test_vague_reply_falls_back_to_the_ranking(
    client, fake_idp, db_session, ai_enabled, monkeypatch
):
    """A reply that promises picks without naming them must still deliver
    real titles rather than an empty shelf."""
    await _build_catalog(db_session)
    from app.ai import embeddings

    await embeddings.embed_missing_titles(db_session)
    await db_session.commit()

    async def vague(db, system, user, max_tokens=800):
        return {"reply": "I found two titles you might enjoy.", "titles": []}

    monkeypatch.setattr(chat.client, "chat_json", vague)

    await do_login(client, fake_idp, LORDO)
    headers = {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}
    body = (
        await client.post("/api/chat", json={"message": "anything good?"}, headers=headers)
    ).json()

    assert body["results"], "the answer carries real titles"
    for card in body["results"]:
        assert card["name"] in body["reply"], "every card is named in the reply"


async def test_a_plain_answer_needs_no_titles(
    client, fake_idp, db_session, ai_enabled, monkeypatch
):
    await _build_catalog(db_session)
    from app.ai import embeddings

    await embeddings.embed_missing_titles(db_session)
    await db_session.commit()

    async def plain(db, system, user, max_tokens=800):
        return {"reply": "Nothing in your catalog is a silent film.", "titles": []}

    monkeypatch.setattr(chat.client, "chat_json", plain)

    await do_login(client, fake_idp, LORDO)
    headers = {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}
    body = (
        await client.post("/api/chat", json={"message": "any silent films?"}, headers=headers)
    ).json()
    assert body["results"] == []
    assert "silent" in body["reply"]
