"""Cache-Aside (Lazy Loading): чтение через кеш, запись сразу в БД."""
from typing import Optional

from cache_client import cache
from database import db
from strategies.base import CacheStrategy


class CacheAsideStrategy(CacheStrategy):
    async def get_item(self, item_id: int) -> Optional[dict]:
        # 1) Пробуем кеш
        cached = await cache.get(item_id)
        if cached is not None:
            return {k: v for k, v in cached.items() if k != "dirty"}

        # 2) Промах — читаем БД и заполняем кеш
        row = await db.get_item(item_id)
        if row is None:
            return None
        await cache.set(item_id, row)
        return row

    async def put_item(self, item_id: int, value: str) -> dict:
        # Запись только в БД; кеш инвалидируем (write-around)
        row = await db.upsert_item(item_id, value)
        await cache.delete(item_id)
        return row
