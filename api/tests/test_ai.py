"""AI stack tests. The shared ai_enabled fixture (conftest) fakes the
embedding space: Coco content on axis 0, the show on axis 1."""

from sqlalchemy import delete, select

from app.ai import client as ai_client
from app.ai import embeddings, taste
from app.models import AuditLog, TitleAITag, TitleEmbedding, User
from tests.util import FRIEND, LORDO, do_login


async def _csrf_headers(client) -> dict:
    return {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}


async def _ingest_both(client, headers):
    await client.get("/api/titles/movie/354912")
    await client.get("/api/titles/tv/456")


async def test_embed_pipeline_and_tags(client, fake_idp, fake_tmdb_http, db_session, ai_enabled):
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    await _ingest_both(client, headers)

    # Ingestion indexes as it goes, so the batch job finds nothing to do.
    rows = (await db_session.execute(select(TitleEmbedding))).scalars().all()
    assert len(rows) == 2, "both titles were indexed the moment they arrived"
    assert await embeddings.embed_missing_titles(db_session) == 0

    # The batch remains the safety net for anything that slipped through.
    await db_session.execute(delete(TitleEmbedding))
    await db_session.commit()
    assert await embeddings.embed_missing_titles(db_session) == 2

    tagged = await embeddings.tag_untagged_titles(db_session)
    assert tagged == 2
    tags = (await db_session.execute(select(TitleAITag))).scalars().all()
    # Deterministic zero-shot: every stored tag respects the floor.
    assert all(t.score >= embeddings.TAG_MIN_SCORE for t in tags if t.score is not None)


async def test_vibe_tags_are_skipped_with_the_local_encoder(
    client, fake_idp, fake_tmdb_http, db_session, ai_enabled
):
    """The bundled encoder is lexical. Measured against the label
    descriptions it tops out around 0.17 versus a floor of 0.40, so it can
    never tag anything, and lowering the floor would attach noise rather
    than meaning. Skipping is the honest behaviour, and it must be a
    deliberate skip rather than a silent no-op that looks like it worked."""
    from app.ai import local_embedding

    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    await _ingest_both(client, headers)

    ai_enabled.embed_model = local_embedding.MODEL_NAME
    await db_session.commit()

    assert await embeddings.tag_untagged_titles(db_session) == 0
    assert (await db_session.execute(select(TitleAITag))).scalars().all() == []


async def test_taste_and_for_you_row(client, fake_idp, fake_tmdb_http, db_session, ai_enabled):
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    await _ingest_both(client, headers)
    await embeddings.embed_missing_titles(db_session)

    # Lordo loved Coco: his taste should sit on axis 0.
    await client.post(
        "/api/history",
        json={"type": "movie", "tmdb_id": 354912, "rating_10": 9, "loved": True},
        headers=headers,
    )
    user = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
    vector = await taste.get_taste(db_session, user)
    assert vector is not None
    assert vector[0] > 0.9
    # Release the row lock on user_tastes before the API session upserts it.
    await db_session.commit()

    home = (await client.get("/api/home", headers=headers)).json()
    keys = [row["key"] for row in home["rows"]]
    assert "for-you" in keys
    for_you = next(row for row in home["rows"] if row["key"] == "for-you")
    # Watched titles are excluded, so Coco itself must not be recommended.
    assert all(item["tmdb_id"] != 354912 for item in for_you["items"])


async def test_movie_night_blend(client, fake_idp, fake_tmdb_http, db_session, ai_enabled):
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    await _ingest_both(client, headers)
    # A third title neither person has watched: the blend candidate.
    await client.get("/api/titles/movie/550")
    await embeddings.embed_missing_titles(db_session)
    await client.post(
        "/api/history",
        json={"type": "movie", "tmdb_id": 354912, "loved": True},
        headers=headers,
    )
    await client.post("/api/auth/logout", headers=headers)

    await do_login(client, fake_idp, FRIEND)
    headers_k = await _csrf_headers(client)
    await client.post(
        "/api/history",
        json={"type": "tv", "tmdb_id": 456, "loved": True},
        headers=headers_k,
    )

    home = (await client.get("/api/home", headers=headers_k)).json()
    keys = [row["key"] for row in home["rows"]]
    assert "movie-night" in keys
    night = next(row for row in home["rows"] if row["key"] == "movie-night")
    names = [item["name"] for item in night["items"]]
    # Titles either person already watched stay out of movie night.
    assert "Coco" not in names
    assert "Example Show" not in names
    assert "Another Film" in names


async def test_nl_search_llm_only_parses(
    client, fake_idp, fake_tmdb_http, db_session, ai_enabled, monkeypatch
):
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    await _ingest_both(client, headers)
    await embeddings.embed_missing_titles(db_session)

    async def fake_chat_json(db, system, user_prompt, max_tokens=800):
        return {
            "mood": "something about music and the afterlife",
            "genres": [],
            "types": ["movie"],
            "runtime_max": 120,
            "year_from": None,
            "year_to": None,
            "on_shared_services": False,
        }

    monkeypatch.setattr(ai_client, "chat_json", fake_chat_json)
    from app.ai import nlsearch

    monkeypatch.setattr(nlsearch.client, "chat_json", fake_chat_json)

    resp = await client.post(
        "/api/ai/search",
        json={"q": "quelque chose comme Coco mais pas anime"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["parsed"]["types"] == ["movie"]
    names = [r["name"] for r in body["results"]]
    # The movie filter drops the show; ranking comes from embeddings.
    assert names == ["Coco"]


async def test_similar_titles(client, fake_idp, fake_tmdb_http, db_session, ai_enabled):
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    await _ingest_both(client, headers)
    await embeddings.embed_missing_titles(db_session)

    resp = await client.get("/api/titles/movie/354912/similar")
    assert resp.status_code == 200
    names = [r["name"] for r in resp.json()["results"]]
    assert "Coco" not in names


async def test_ai_disabled_degrades(client, fake_idp, fake_tmdb_http, db_session):
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)

    resp = await client.post("/api/ai/search", json={"q": "anything"}, headers=headers)
    assert resp.status_code == 503
    assert resp.json()["detail"] == "ai_disabled"

    home = await client.get("/api/home", headers=headers)
    assert home.status_code == 200
    assert "for-you" not in [r["key"] for r in home.json()["rows"]]

    similar = await client.get("/api/titles/movie/354912/similar")
    assert similar.status_code == 200
    assert similar.json()["results"] == []


async def test_admin_ai_settings_roundtrip(client, fake_idp, db_session):
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)

    current = (await client.get("/api/admin/settings/ai")).json()
    assert current["enabled"] is False

    updated = await client.put(
        "/api/admin/settings/ai",
        json={
            "enabled": True,
            "base_url": "https://ai.example.com/v1/",
            "chat_model": "gemma-4-26b-a4b-it",
            "embed_model": "text-embedding-nomic-embed-text-v1.5",
            "api_key": "super-secret",
        },
        headers=headers,
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["enabled"] is True
    assert body["base_url"] == "https://ai.example.com/v1"
    assert body["has_api_key"] is True

    # Key is encrypted at rest and decrypts back.
    from app.ai import crypto
    from app.models import AISettings

    row = (await db_session.execute(select(AISettings))).scalar_one()
    assert row.api_key_enc != "super-secret"
    assert crypto.decrypt(row.api_key_enc) == "super-secret"

    actions = (await db_session.execute(select(AuditLog.action))).scalars().all()
    assert "settings.ai_update" in actions


async def test_admin_ai_settings_member_forbidden(claimed, client, fake_idp):
    await do_login(client, fake_idp, FRIEND)
    assert (await client.get("/api/admin/settings/ai")).status_code == 403
