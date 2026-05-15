"""Обёртка над Redis: get/set, флаг dirty для Write-Back."""
import json
from typing import Optional

import redis.asyncio as redis

from config import CACHE_TTL_SEC, REDIS_URL
from metrics import metrics


class CacheClient:
    def __init__(self) -> None:
        self.client: Optional[redis.Redis] = None

    async def connect(self) -> None:
        self.client = redis.from_url(REDIS_URL, decode_responses=True)

    async def close(self) -> None:
        if self.client:
            await self.client.aclose()

    def _key(self, item_id: int) -> str:
        return f"item:{item_id}"

    async def get_raw(self, item_id: int) -> Optional[dict]:
        """Чтение без учёта hit/miss (для внутреннего flush)."""
        assert self.client is not None
        raw = await self.client.get(self._key(item_id))
        return json.loads(raw) if raw else None

    async def get(self, item_id: int) -> Optional[dict]:
        data = await self.get_raw(item_id)
        if data is None:
            metrics.inc("cache_misses")
            return None
        metrics.inc("cache_hits")
        return data

    async def set(self, item_id: int, payload: dict, dirty: bool = False) -> None:
        assert self.client is not None
        payload = {**payload, "dirty": dirty}
        await self.client.setex(
            self._key(item_id), CACHE_TTL_SEC, json.dumps(payload, default=str)
        )

    async def delete(self, item_id: int) -> None:
        assert self.client is not None
        await self.client.delete(self._key(item_id))

    async def mark_dirty(self, item_id: int, payload: dict) -> None:
        """Write-Back: запись только в кеш, помечаем dirty."""
        await self.set(item_id, payload, dirty=True)
        metrics.inc("write_back_dirty")

    async def list_dirty_keys(self, limit: int) -> list[int]:
        assert self.client is not None
        dirty_ids: list[int] = []
        async for key in self.client.scan_iter(match="item:*", count=200):
            raw = await self.client.get(key)
            if not raw:
                continue
            data = json.loads(raw)
            if data.get("dirty"):
                dirty_ids.append(int(key.split(":", 1)[1]))
                if len(dirty_ids) >= limit:
                    break
        return dirty_ids

    async def clear_dirty_flag(self, item_id: int, payload: dict) -> None:
        await self.set(item_id, payload, dirty=False)


cache = CacheClient()
