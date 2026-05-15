"""Слой PostgreSQL: чтение и запись сущностей items."""
from typing import Optional

import asyncpg

from config import DATABASE_URL
from metrics import metrics


class Database:
    def __init__(self) -> None:
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

    async def get_item(self, item_id: int) -> Optional[dict]:
        assert self.pool is not None
        metrics.inc("db_reads")
        row = await self.pool.fetchrow(
            "SELECT id, value, updated_at FROM items WHERE id = $1", item_id
        )
        if not row:
            return None
        return {
            "id": row["id"],
            "value": row["value"],
            "updated_at": row["updated_at"].isoformat(),
        }

    async def upsert_item(self, item_id: int, value: str) -> dict:
        assert self.pool is not None
        metrics.inc("db_writes")
        row = await self.pool.fetchrow(
            """
            INSERT INTO items (id, value, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (id) DO UPDATE
            SET value = EXCLUDED.value, updated_at = NOW()
            RETURNING id, value, updated_at
            """,
            item_id,
            value,
        )
        return {
            "id": row["id"],
            "value": row["value"],
            "updated_at": row["updated_at"].isoformat(),
        }


db = Database()
