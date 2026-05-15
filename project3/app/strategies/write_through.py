"""Write-Through: при записи обновляем и кеш, и БД синхронно."""
from typing import Optional

from cache_client import cache
from database import db
from strategies.base import CacheStrategy


class WriteThroughStrategy(CacheStrategy):
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
        # Сначала БД, затем актуальная копия в кеше
        row = await db.upsert_item(item_id, value)
        await cache.set(item_id, row)
        return row
