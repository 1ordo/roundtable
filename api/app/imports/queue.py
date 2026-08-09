"""Thin arq enqueue wrapper, patched out in tests to run inline."""

import uuid

from arq import create_pool
from arq.connections import RedisSettings

from app.config import get_settings


async def enqueue_process_batch(batch_id: uuid.UUID) -> None:
    pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    try:
        await pool.enqueue_job("process_import_batch", str(batch_id))
    finally:
        await pool.aclose()
