"""Batch processing: parse results are stored on the batch row, the worker
matches them against TMDB and applies what it can, and everything uncertain
waits in the review queue."""

import copy
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import ingest, tmdb
from app.imports.matcher import match_row
from app.models import ImportBatch, User, WatchEvent
from app.tracking import service as lists_service

logger = logging.getLogger("watchpile.imports")


def _parse_watched_at(value: str | None) -> datetime:
    if value:
        try:
            return datetime.fromisoformat(value).replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.now(UTC)


async def _apply_row(
    db: AsyncSession,
    user: User,
    batch: ImportBatch,
    candidate: dict,
    watched_at: str | None,
) -> str:
    """Create the watch event or list item for a matched candidate.
    Returns imported | skipped."""
    title = await ingest.ensure_title(db, candidate["type"], candidate["tmdb_id"])
    if batch.target == "history":
        when = _parse_watched_at(watched_at)
        existing = (
            await db.execute(
                select(WatchEvent).where(
                    WatchEvent.user_id == user.id,
                    WatchEvent.title_id == title.id,
                    WatchEvent.watched_at == when,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return "skipped"
        db.add(
            WatchEvent(
                user_id=user.id,
                title_id=title.id,
                watched_at=when,
                source="import",
                import_batch_id=batch.id,
                loved=False,
            )
        )
        await db.flush()
        return "imported"

    watchlist = await lists_service.ensure_watchlist(db, user)
    await lists_service.add_title_to_list(db, watchlist, title.id, user)
    return "imported"


async def process_batch(db: AsyncSession, batch_id: uuid.UUID) -> None:
    batch = (
        await db.execute(select(ImportBatch).where(ImportBatch.id == batch_id))
    ).scalar_one_or_none()
    if batch is None or batch.status not in ("pending", "processing"):
        return
    user = (await db.execute(select(User).where(User.id == batch.user_id))).scalar_one()

    batch.status = "processing"
    await db.commit()

    stats = {"total": len(batch.rows), "imported": 0, "ambiguous": 0, "unmatched": 0, "skipped": 0}
    review: list[dict] = []
    seen_names: dict[tuple, tuple[str, list[dict]]] = {}

    try:
        for index, row in enumerate(batch.rows):
            key = (row["name"].lower(), row.get("type_hint"), row.get("year"))
            if key in seen_names:
                status, candidates = seen_names[key]
            else:
                status, candidates = await match_row(
                    db, row["name"], row.get("type_hint"), row.get("year")
                )
                seen_names[key] = (status, candidates)

            if status == "matched":
                outcome = await _apply_row(db, user, batch, candidates[0], row.get("watched_at"))
                stats[outcome] += 1
            elif status == "ambiguous":
                stats["ambiguous"] += 1
                review.append(
                    {
                        "index": index,
                        "raw": row["raw"],
                        "name": row["name"],
                        "watched_at": row.get("watched_at"),
                        "candidates": candidates,
                        "resolved": False,
                    }
                )
            else:
                stats["unmatched"] += 1
    except tmdb.TmdbNotConfigured:
        batch.status = "failed"
        batch.error = "TMDB API key is not configured"
        await db.commit()
        return
    except Exception:
        logger.exception("import batch %s failed", batch_id)
        batch.status = "failed"
        batch.error = "processing failed, see server logs"
        await db.commit()
        return

    batch.stats = stats
    batch.review_queue = review
    batch.status = "review" if review else "done"
    await db.commit()


async def resolve_review_item(
    db: AsyncSession, batch: ImportBatch, user: User, index: int, tmdb_id: int, media_type: str
) -> None:
    queue = list(batch.review_queue or [])
    entry = next((e for e in queue if e["index"] == index and not e["resolved"]), None)
    if entry is None:
        raise ValueError("review item not found or already resolved")
    outcome = await _apply_row(
        db,
        user,
        batch,
        {"tmdb_id": tmdb_id, "type": media_type},
        entry.get("watched_at"),
    )
    # Deep-copy the queue before mutating: a shallow copy shares its entry
    # dicts with the loaded value, so SQLAlchemy would see old == new and
    # skip the UPDATE entirely.
    queue = copy.deepcopy(queue)
    next(e for e in queue if e["index"] == index)["resolved"] = True
    batch.review_queue = queue
    stats = dict(batch.stats or {})
    stats[outcome] = stats.get(outcome, 0) + 1
    stats["ambiguous"] = max(0, stats.get("ambiguous", 1) - 1)
    batch.stats = stats
    if all(e["resolved"] for e in queue):
        batch.status = "done"
    await db.flush()


async def dismiss_review_item(db: AsyncSession, batch: ImportBatch, index: int) -> None:
    queue = list(batch.review_queue or [])
    entry = next((e for e in queue if e["index"] == index and not e["resolved"]), None)
    if entry is None:
        raise ValueError("review item not found or already resolved")
    queue = copy.deepcopy(queue)
    next(e for e in queue if e["index"] == index)["resolved"] = True
    batch.review_queue = queue
    stats = dict(batch.stats or {})
    stats["unmatched"] = stats.get("unmatched", 0) + 1
    stats["ambiguous"] = max(0, stats.get("ambiguous", 1) - 1)
    batch.stats = stats
    if all(e["resolved"] for e in queue):
        batch.status = "done"
    await db.flush()
