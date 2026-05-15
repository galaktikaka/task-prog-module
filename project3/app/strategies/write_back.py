"""Write-Back: запись в кеш сразу, в БД — пакетами по таймеру."""
import asyncio
import logging
from typing import Optional

from cache_client import cache
from config import WRITE_BACK_FLUSH_BATCH_SIZE, WRITE_BACK_FLUSH_INTERVAL_SEC
from database import db
from metrics import metrics
from strategies.base import CacheStrategy

logger = logging.getLogger(__name__)


class WriteBackStrategy(CacheStrategy):
    def __init__(self) -> None:
        self._flush_task: Optional[asyncio.Task] = None

    def start_background_flush(self) -> None:
        if self._flush_task is None:
            self._flush_task = asyncio.create_task(self._flush_loop())

    async def stop_background_flush(self) -> None:
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None

    async def get_item(self, item_id: int) -> Optional[dict]:
        cached = await cache.get(item_id)
        if cached is not None:
            return {k: v for k, v in cached.items() if k != "dirty"}

        row = await db.get_item(item_id)
        if row is None:
            return None
        await cache.set(item_id, row)
        return row

    async def put_item(self, item_id: int, value: str) -> dict:
        # Быстрый ответ клиенту — только Redis
        payload = {"id": item_id, "value": value, "updated_at": None}
        await cache.mark_dirty(item_id, payload)
        return {"id": item_id, "value": value}

    async def flush(self) -> dict:
        """Сброс накопленных dirty-записей в PostgreSQL."""
        dirty_ids = await cache.list_dirty_keys(WRITE_BACK_FLUSH_BATCH_SIZE)
        flushed = 0
        for item_id in dirty_ids:
            cached = await cache.get_raw(item_id)
            if cached is None or not cached.get("dirty"):
                continue
            row = await db.upsert_item(item_id, cached["value"])
            await cache.clear_dirty_flag(item_id, row)
            flushed += 1

        if flushed:
            metrics.inc("write_back_flushes")
            metrics.inc("write_back_flushed_items", flushed)
            logger.info("Write-Back flush: %d items -> DB", flushed)

        return {"flushed": flushed, "pending_scan": len(dirty_ids)}

    async def _flush_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(WRITE_BACK_FLUSH_INTERVAL_SEC)
                result = await self.flush()
                if result["flushed"]:
                    logger.info(
                        "Background flush every %ss: %s items",
                        WRITE_BACK_FLUSH_INTERVAL_SEC,
                        result["flushed"],
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Write-Back flush error")
