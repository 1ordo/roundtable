"""Test harness: a disposable pgvector Postgres via testcontainers, migrations
applied once, tables truncated between tests, OIDC faked at the provider seam.

The container starts at import time so the database URL is in the environment
before any app module reads settings."""

import os

# pytest_sessionfinish stops the Postgres container itself; the Ryuk reaper
# only adds a flaky moving part on local Docker Desktop.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

from testcontainers.postgres import PostgresContainer  # noqa: E402

_pg = PostgresContainer("pgvector/pgvector:pg17", username="test", password="test", dbname="test")
_pg.start()

os.environ["RT_DATABASE_URL"] = (
    f"postgresql+asyncpg://test:test@127.0.0.1:{_pg.get_exposed_port(5432)}/test"
)
os.environ["RT_ENV"] = "test"
os.environ["RT_SECRET_KEY"] = "test-secret"
os.environ["RT_COOKIE_SECURE"] = "false"
os.environ["RT_OIDC_CLIENT_ID"] = "test-client"
os.environ["RT_OIDC_CLIENT_SECRET"] = "test-secret"
os.environ["RT_PUBLIC_BASE_URL"] = "http://test"
# The shipped default is empty on purpose; tests promote their own admin.
os.environ["RT_BOOTSTRAP_ADMIN_USERNAMES"] = "Lordo"

from collections.abc import AsyncIterator  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from alembic import command  # noqa: E402
from app.auth import oidc  # noqa: E402
from app.db import get_engine, get_sessionmaker  # noqa: E402
from app.main import app  # noqa: E402

API_DIR = Path(__file__).resolve().parents[1]

ALL_TABLES = (
    "sessions, audit_log, users, tenants, ai_settings, quota_usage, feature_flags, "
    "availability, titles, api_cache, list_items, lists, watch_events, import_batches, "
    "title_embeddings, title_ai_tags, label_embeddings, user_tastes, api_tokens, "
    "notifications, interactions, groups, auth_settings"
)


def pytest_sessionfinish(session, exitstatus):
    _pg.stop()


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def no_imdb_guide(monkeypatch) -> None:
    """The parents guide calls IMDb over the network. Tests never do, so the
    default is "IMDb has nothing", which exercises the estimate fallback.
    A test that wants the real path patches this itself."""
    from app.catalog import imdb_guide

    async def none(db, title):
        return None

    monkeypatch.setattr(imdb_guide, "for_title", none)


@pytest.fixture(autouse=True)
async def reset_login_limiter(monkeypatch) -> None:
    """The sign-in limiter lives in Redis, which is shared across the run.
    Without this, failed attempts from one test would lock out the next."""
    counters: dict[str, int] = {}

    async def too_many(username: str) -> bool:
        from app.auth import passwords as pw

        return counters.get(username.lower(), 0) >= pw.MAX_ATTEMPTS

    async def record(username: str) -> None:
        counters[username.lower()] = counters.get(username.lower(), 0) + 1

    async def clear(username: str) -> None:
        counters.pop(username.lower(), None)

    from app.auth import passwords as pw

    monkeypatch.setattr(pw, "too_many_attempts", too_many)
    monkeypatch.setattr(pw, "record_failure", record)
    monkeypatch.setattr(pw, "clear_failures", clear)


@pytest.fixture(autouse=True)
async def clean_db(migrated_db) -> AsyncIterator[None]:
    yield
    async with get_engine().begin() as conn:
        await conn.execute(text(f"TRUNCATE {ALL_TABLES} CASCADE"))


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


@pytest.fixture
async def claimed() -> None:
    """An instance that already has an owner.

    The first account on an empty instance becomes its admin, because a
    fresh install with no admin and no way to make one is not an install.
    That rule makes "the first person to sign in during this test" an admin,
    which is the wrong premise for any test about what an ordinary member
    may do. Seeding an owner directly puts the instance in the state every
    real one is in by the time a second person arrives.
    """
    from app.auth.service import get_default_tenant
    from app.models import User

    async with get_sessionmaker()() as session:
        tenant = await get_default_tenant(session)
        session.add(
            User(
                tenant_id=tenant.id,
                username="instance-owner",
                email="owner@test",
                role="admin",
                services=[],
                prefs={},
                api_enabled=False,
                is_active=True,
            )
        )
        await session.commit()


class FakeOIDCProvider:
    """Stands in for Pocket ID. Tests set .claims to control the identity."""

    def __init__(self) -> None:
        self.claims: dict = {}
        self.fail_exchange = False

    async def authorize_url(self, state: str, nonce: str, code_challenge: str) -> str:
        return f"https://idp.test/authorize?state={state}&nonce={nonce}"

    async def exchange_code(self, code: str, code_verifier: str) -> dict:
        if self.fail_exchange:
            raise oidc.OIDCError("exchange failed")
        return {"id_token": "fake-id-token"}

    async def verify_id_token(self, id_token: str, nonce: str) -> dict:
        return self.claims


@pytest.fixture
def fake_idp(monkeypatch) -> FakeOIDCProvider:
    fake = FakeOIDCProvider()
    monkeypatch.setattr(oidc, "provider", fake)
    return fake


@pytest.fixture
def tmdb_key(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "tmdb_api_key", "test-key")


@pytest.fixture
def fake_tmdb_http(monkeypatch):
    """Intercept the raw HTTP layer so caching and quota logic stay real."""
    from app.catalog import quota, tmdb
    from tests import fixtures

    calls: list[str] = []

    async def _fake(db, path, params=None):
        calls.append(path)
        await quota.bump(db, "tmdb")
        if path.startswith("/trending/movie"):
            return fixtures.TRENDING_MOVIES
        if path.startswith("/trending/tv"):
            return {"page": 1, "total_pages": 1, "results": []}
        if path.startswith("/discover/"):
            return {"page": 1, "total_pages": 1, "results": []}
        if path.startswith("/search/multi"):
            q = str((params or {}).get("query", "")).lower()
            if "coco" in q or "example" in q:
                return fixtures.SEARCH_MULTI
            return {"page": 1, "total_pages": 1, "results": []}
        if path.startswith("/genre/"):
            return {"genres": [{"id": 16, "name": "Animation"}]}
        if path.startswith("/movie/now_playing") or path.startswith("/movie/upcoming"):
            return fixtures.TRENDING_MOVIES
        if path.startswith("/tv/on_the_air"):
            return fixtures.ON_THE_AIR
        if path.startswith("/watch/providers/"):
            return fixtures.PROVIDER_LIST
        if path.startswith("/movie/354912"):
            return fixtures.MOVIE_DETAILS
        if path.startswith("/movie/550"):
            return fixtures.MOVIE2_DETAILS
        if path.startswith("/movie/777"):
            # A third film, so franchise tests can have a part beyond the
            # two detailed fixtures without inventing a whole payload.
            return {
                **fixtures.MOVIE2_DETAILS,
                "id": 777,
                "title": "Third One",
                "release_date": "2024-01-01",
            }
        if path.startswith("/tv/456"):
            return fixtures.TV_DETAILS
        raise tmdb.TmdbError(f"unexpected path {path}")

    monkeypatch.setattr(tmdb, "_http_get", _fake)
    return calls


def fake_vector_for(text: str) -> list[float]:
    """Deterministic fake embedding space: Coco content on axis 0, the show
    on axis 1, everything else a stable pseudo-random unit vector."""
    import hashlib

    import numpy as np

    lower = text.lower()
    vector = np.zeros(768)
    if "coco" in lower:
        vector[0] = 1.0
        return vector.tolist()
    if "example show" in lower:
        vector[1] = 1.0
        return vector.tolist()
    if "afterlife" in lower or "music" in lower:
        vector[0], vector[1] = 0.9, 0.1
        vector /= np.linalg.norm(vector)
        return vector.tolist()
    seed = int.from_bytes(hashlib.sha256(lower.encode()).digest()[:4], "big")
    rng = np.random.default_rng(seed)
    vector = rng.normal(size=768)
    vector /= np.linalg.norm(vector)
    return vector.tolist()


@pytest.fixture
async def ai_enabled(db_session, monkeypatch):
    from app.ai import client as ai_client
    from app.ai import embeddings as embeddings_module

    settings = await ai_client.get_ai_settings(db_session)
    settings.enabled = True
    # Stands for a real embedding endpoint, which is what the fake encoder
    # below is imitating. Leaving the local model name here would be a
    # different configuration entirely: the local encoder is lexical and
    # cannot do zero-shot tagging, so tagging is skipped under it by design.
    settings.embed_model = "test-embedding-model"
    await db_session.commit()

    async def fake_embed(db, texts):
        return [fake_vector_for(t) for t in texts]

    monkeypatch.setattr(ai_client, "embed_texts", fake_embed)
    monkeypatch.setattr(embeddings_module.client, "embed_texts", fake_embed)
    return settings
