import numpy as np
from sqlalchemy import select

from app.ai import embeddings, taste
from app.models import Interaction, Title, TitleEmbedding, User
from tests.util import FRIEND, LORDO, do_login


async def _csrf_headers(client) -> dict:
    return {"X-CSRF-Token": (await client.get("/api/me")).json()["csrf"]}


async def test_signal_lifecycle(client, fake_idp, fake_tmdb_http, db_session):
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    await client.get("/api/titles/movie/354912")

    # Views dedupe within the window.
    for _ in range(3):
        resp = await client.post(
            "/api/titles/movie/354912/signal", json={"kind": "view"}, headers=headers
        )
        assert resp.status_code == 200
    views = (
        (await db_session.execute(select(Interaction).where(Interaction.kind == "view")))
        .scalars()
        .all()
    )
    assert len(views) == 1

    # Like, then dislike replaces it, then dislike again toggles off.
    liked = await client.post(
        "/api/titles/movie/354912/signal", json={"kind": "like"}, headers=headers
    )
    assert liked.json() == {"liked": True, "disliked": False}
    disliked = await client.post(
        "/api/titles/movie/354912/signal", json={"kind": "dislike"}, headers=headers
    )
    assert disliked.json() == {"liked": False, "disliked": True}
    toggled = await client.post(
        "/api/titles/movie/354912/signal", json={"kind": "dislike"}, headers=headers
    )
    assert toggled.json() == {"liked": False, "disliked": False}


async def test_likes_shape_taste_without_watching(
    client, fake_idp, fake_tmdb_http, db_session, ai_enabled
):
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    await client.get("/api/titles/movie/354912")
    await client.get("/api/titles/tv/456")
    await embeddings.embed_missing_titles(db_session)

    # No watch history at all: a like alone must produce a taste on axis 0.
    await client.post("/api/titles/movie/354912/signal", json={"kind": "like"}, headers=headers)
    user = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
    vector = await taste.get_taste(db_session, user)
    await db_session.commit()
    assert vector is not None
    assert vector[0] > 0.9


async def test_dislike_pushes_taste_away_and_hides_title(
    client, fake_idp, fake_tmdb_http, db_session, ai_enabled
):
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    await client.get("/api/titles/movie/354912")
    await client.get("/api/titles/tv/456")
    await client.get("/api/titles/movie/550")
    await embeddings.embed_missing_titles(db_session)

    await client.post("/api/titles/movie/354912/signal", json={"kind": "like"}, headers=headers)
    await client.post("/api/titles/tv/456/signal", json={"kind": "dislike"}, headers=headers)

    user = (await db_session.execute(select(User).where(User.username == "Lordo"))).scalar_one()
    excluded = await taste.watched_title_ids(db_session, user)
    show = (await db_session.execute(select(Title).where(Title.tmdb_id == 456))).scalar_one()
    assert show.id in excluded, "disliked titles never come back as recommendations"


async def test_diversified_ranking_breaks_bubble(db_session, ai_enabled, fake_tmdb_http):
    """Fifteen near-identical horror titles and one popular outlier: the naive
    top list is all horror, the diversified list still tries something else."""
    from app.ai.client import get_ai_settings

    settings = await get_ai_settings(db_session)
    model = settings.embed_model

    def vec(axis0: float, axis1: float) -> list[float]:
        v = np.zeros(768)
        v[0], v[1] = axis0, axis1
        v /= np.linalg.norm(v)
        return v.tolist()

    for i in range(15):
        title = Title(
            tmdb_id=90000 + i,
            type="movie",
            name=f"Horror {i}",
            genres=[{"id": 27, "name": "Horror"}],
            poster_path=f"/h{i}.jpg",
            popularity=10.0,
        )
        db_session.add(title)
        await db_session.flush()
        db_session.add(TitleEmbedding(title_id=title.id, model=model, embedding=vec(1.0, 0.01 * i)))
    outlier = Title(
        tmdb_id=91000,
        type="movie",
        name="Beloved Comedy",
        genres=[{"id": 35, "name": "Comedy"}],
        poster_path="/c.jpg",
        popularity=99.0,
    )
    db_session.add(outlier)
    await db_session.flush()
    db_session.add(TitleEmbedding(title_id=outlier.id, model=model, embedding=vec(0.1, 1.0)))
    await db_session.commit()

    horror_taste = np.zeros(768)
    horror_taste[0] = 1.0

    naive = await taste.rank_titles_by_vector(db_session, horror_taste, limit=10)
    assert all("Horror" in t.name for t, _ in naive)

    diverse = await taste.diversified_ranking(db_session, horror_taste, limit=10)
    names = [t.name for t, _ in diverse]
    assert "Beloved Comedy" in names, "exploration slots must escape the bubble"
    assert sum("Horror" in n for n in names) >= 6, "taste still dominates"


async def test_onboarding_prefs_roundtrip(client, fake_idp):
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)

    me = (await client.get("/api/me")).json()
    assert me["needs_onboarding"] is True

    resp = await client.put(
        "/api/me",
        json={"country_code": "eg", "languages": ["AR", "en", "fr"], "genres": [27, 35]},
        headers=headers,
    )
    assert resp.status_code == 200
    me = (await client.get("/api/me")).json()
    assert me["needs_onboarding"] is False
    assert me["user"]["prefs"]["languages"] == ["ar", "en", "fr"]
    assert me["user"]["prefs"]["genres"] == [27, 35]


async def test_groups_crud_and_suggestions(
    client, fake_idp, fake_tmdb_http, db_session, ai_enabled
):
    # Nadia exists and has taste on axis 1.
    await do_login(client, fake_idp, FRIEND)
    headers_k = await _csrf_headers(client)
    await client.get("/api/titles/tv/456")
    await client.get("/api/titles/movie/354912")
    await client.get("/api/titles/movie/550")
    await embeddings.embed_missing_titles(db_session)
    await client.post("/api/titles/tv/456/signal", json={"kind": "like"}, headers=headers_k)
    await client.post("/api/auth/logout", headers=headers_k)

    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    await client.post("/api/titles/movie/354912/signal", json={"kind": "like"}, headers=headers)

    missing = await client.post(
        "/api/groups", json={"name": "Ghosts", "member_usernames": ["nobody"]}, headers=headers
    )
    assert missing.status_code == 404

    created = await client.post(
        "/api/groups",
        json={"name": "Movie night", "member_usernames": ["Nadia"]},
        headers=headers,
    )
    assert created.status_code == 201
    group = created.json()
    assert sorted(group["members"]) == ["Lordo", "Nadia"]

    suggestions = await client.post(
        f"/api/groups/{group['id']}/suggestions",
        json={"weights": {"Nadia": 2.0}},
        headers=headers,
    )
    assert suggestions.status_code == 200
    body = suggestions.json()
    assert body["without_taste"] == []
    names = [r["name"] for r in body["results"]]
    assert "Another Film" in names or len(names) > 0

    listed = (await client.get("/api/groups", headers=headers)).json()
    assert len(listed) == 1

    gone = await client.delete(f"/api/groups/{group['id']}", headers=headers)
    assert gone.status_code == 204
    assert (await client.get("/api/groups", headers=headers)).json() == []


async def test_new_page_rows(client, fake_idp, fake_tmdb_http, db_session):
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    await client.put("/api/me", json={"country_code": "EG"}, headers=headers)
    # Ingest Coco so its EG availability counts as fresh (first_seen = now).
    await client.get("/api/titles/movie/354912")

    resp = await client.get("/api/new")
    assert resp.status_code == 200
    body = resp.json()
    rows = {row["key"]: row for row in body["rows"]}
    assert "in-theaters" in rows
    assert "upcoming" in rows
    assert "new-series" in rows

    # Coco's EG availability is on Disney Plus, so it appears under that
    # service once the person subscribes to it.
    await client.put("/api/me", json={"services": [337]}, headers=headers)
    body = (await client.get("/api/new")).json()
    sections = {s["service"]["name"]: s for s in body["services"]}
    assert list(sections) == ["Disney+"], "only services the person pays for"
    assert any(item["name"] == "Coco" for item in sections["Disney+"]["items"])
    assert sections["Disney+"]["unknown"] is False


async def test_admin_activity(client, fake_idp, fake_tmdb_http, db_session):
    await do_login(client, fake_idp, LORDO)
    headers = await _csrf_headers(client)
    await client.get("/api/titles/movie/354912")
    await client.post("/api/titles/movie/354912/signal", json={"kind": "view"}, headers=headers)
    await client.post("/api/titles/movie/354912/signal", json={"kind": "like"}, headers=headers)

    resp = await client.get("/api/admin/activity")
    assert resp.status_code == 200
    body = resp.json()
    assert body["by_kind_30d"]["view"] == 1
    assert body["by_kind_30d"]["like"] == 1
    assert body["top_viewed"][0]["name"] == "Coco"
    assert body["per_user"][0]["username"] == "Lordo"


async def test_activity_admin_only(claimed, client, fake_idp):
    await do_login(client, fake_idp, FRIEND)
    assert (await client.get("/api/admin/activity")).status_code == 403
