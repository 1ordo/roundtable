"""Embedding pipeline: turn titles into vectors, labels into centroids, and
titles into vibe tags. All deterministic given the same model."""

import logging
import uuid
from datetime import UTC, datetime

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import client, local_embedding
from app.ai.labels import VIBE_LABELS
from app.models import LabelEmbedding, Title, TitleAITag, TitleEmbedding

logger = logging.getLogger("watchpile.ai")

BATCH_SIZE = 16
TAG_TOP_K = 4
TAG_MIN_SCORE = 0.40


def build_title_text(title: Title) -> str:
    """Full context per the plan: name, genres, keywords, and the whole
    overview, not a truncated snippet."""
    parts = [f"{title.name} ({title.year})" if title.year else title.name]
    if title.original_name and title.original_name != title.name:
        parts.append(f"Original title: {title.original_name}")
    parts.append("Series." if title.type == "tv" else "Film.")
    if title.genres:
        parts.append("Genres: " + ", ".join(g.get("name", "") for g in title.genres))
    if title.keywords:
        parts.append("Keywords: " + ", ".join(title.keywords[:40]))
    if title.overview:
        parts.append(title.overview)
    return "\n".join(p for p in parts if p)


async def embed_missing_titles(db: AsyncSession, limit: int = 200) -> int:
    """Embed titles that have no vector for the current model."""
    settings = await client.require_ai(db)
    model = settings.embed_model
    rows = (
        (
            await db.execute(
                select(Title)
                .outerjoin(
                    TitleEmbedding,
                    (TitleEmbedding.title_id == Title.id) & (TitleEmbedding.model == model),
                )
                .where(TitleEmbedding.title_id.is_(None))
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    done = 0
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start : start + BATCH_SIZE]
        vectors = await client.embed_texts(db, [build_title_text(t) for t in batch])
        for title, vector in zip(batch, vectors, strict=True):
            await db.execute(delete(TitleEmbedding).where(TitleEmbedding.title_id == title.id))
            db.add(TitleEmbedding(title_id=title.id, model=model, embedding=vector))
        await db.commit()
        done += len(batch)
    if done:
        logger.info("embedded %d titles", done)
    return done


async def ensure_label_embeddings(db: AsyncSession) -> dict[str, np.ndarray]:
    settings = await client.require_ai(db)
    model = settings.embed_model
    existing = {
        row.tag: np.array(row.embedding)
        for row in (
            await db.execute(select(LabelEmbedding).where(LabelEmbedding.model == model))
        ).scalars()
    }
    missing = [tag for tag in VIBE_LABELS if tag not in existing]
    if missing:
        vectors = await client.embed_texts(db, [VIBE_LABELS[tag] for tag in missing])
        for tag, vector in zip(missing, vectors, strict=True):
            db.add(LabelEmbedding(tag=tag, model=model, embedding=vector))
            existing[tag] = np.array(vector)
        await db.commit()
    return existing


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


async def tag_untagged_titles(db: AsyncSession, limit: int = 300) -> int:
    """Zero-shot vibe tags for titles that have an embedding but no ai tags
    for the current model.

    Needs a real embedding model. The bundled encoder is hashed n-grams,
    which is lexical: it compares the words two texts share, and a title
    synopsis shares almost no words with a phrase like "quietly devastating".
    Measured, the best score any real title reaches against any label is
    about 0.17 against a floor of 0.40, so nothing is ever tagged.

    Lowering the floor is the wrong fix. At those scores the ranking is
    noise, and the top match for a given film is as likely to be unrelated
    as apt, so a lower floor buys wrong tags rather than right ones. Skipping
    is honest: vibe tags are a feature of having a real embedding endpoint.
    """
    settings = await client.require_ai(db)
    model = settings.embed_model
    if model == local_embedding.MODEL_NAME:
        logger.info("vibe tags need a real embedding model; skipping with the local encoder")
        return 0
    labels = await ensure_label_embeddings(db)

    tagged_ids = select(TitleAITag.title_id).where(
        TitleAITag.source == "ai", TitleAITag.model == model
    )
    rows = (
        (
            await db.execute(
                select(TitleEmbedding)
                .where(TitleEmbedding.model == model, TitleEmbedding.title_id.not_in(tagged_ids))
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        vector = np.array(row.embedding)
        scored = sorted(
            ((tag, _cosine(vector, centroid)) for tag, centroid in labels.items()),
            key=lambda pair: -pair[1],
        )
        for tag, score in scored[:TAG_TOP_K]:
            if score < TAG_MIN_SCORE:
                continue
            db.add(
                TitleAITag(title_id=row.title_id, tag=tag, source="ai", model=model, score=score)
            )
    await db.commit()
    if rows:
        logger.info("tagged %d titles", len(rows))
    return len(rows)


async def get_title_tags(db: AsyncSession, title_id: uuid.UUID) -> list[dict]:
    rows = (
        (
            await db.execute(
                select(TitleAITag)
                .where(TitleAITag.title_id == title_id, TitleAITag.source == "ai")
                .order_by(TitleAITag.score.desc())
            )
        )
        .scalars()
        .all()
    )
    return [{"tag": r.tag, "score": r.score} for r in rows]


def utcnow() -> datetime:
    return datetime.now(UTC)


async def embed_title_now(db: AsyncSession, title: Title) -> bool:
    """Give one title its vector immediately.

    Called the moment a title enters the catalog, so anything the viewer
    opens or saves can be recommended straight away instead of waiting for
    the next batch. Best effort: a failure here must never stop a page from
    rendering, it just leaves the title for the batch job."""
    try:
        settings = await client.require_ai(db)
        existing = (
            await db.execute(
                select(TitleEmbedding).where(
                    TitleEmbedding.title_id == title.id,
                    TitleEmbedding.model == settings.embed_model,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return False
        vectors = await client.embed_texts(db, [build_title_text(title)])
        db.add(
            TitleEmbedding(
                title_id=title.id,
                model=settings.embed_model,
                embedding=vectors[0],
                created_at=datetime.now(UTC),
            )
        )
        await db.flush()
        return True
    except (client.AIDisabled, client.AIError):
        return False
    except Exception:
        logger.warning("could not embed %s on ingest", title.name, exc_info=False)
        return False
