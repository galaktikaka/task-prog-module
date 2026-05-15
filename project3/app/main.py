"""HTTP API: одинаковые эндпоинты, стратегия кеша выбирается через CACHE_STRATEGY."""
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from cache_client import cache
from config import CACHE_STRATEGY
from database import db
from metrics import metrics
from strategies import create_strategy
from strategies.write_back import WriteBackStrategy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app")

strategy = create_strategy()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.connect()
    await cache.connect()
    logger.info("Started with strategy=%s", CACHE_STRATEGY)
    if isinstance(strategy, WriteBackStrategy):
        strategy.start_background_flush()
    yield
    if isinstance(strategy, WriteBackStrategy):
        await strategy.stop_background_flush()
        await strategy.flush()
    await cache.close()
    await db.close()


app = FastAPI(title="Cache Comparison App", lifespan=lifespan)


class ItemWrite(BaseModel):
    value: str = Field(min_length=1, max_length=256)


@app.get("/health")
async def health():
    return {"status": "ok", "strategy": CACHE_STRATEGY}


@app.post("/admin/reset-metrics")
async def reset_metrics():
    metrics.reset()
    return {"status": "metrics_reset"}


@app.post("/admin/flush")
async def admin_flush():
    return await strategy.flush()


@app.get("/metrics")
async def get_metrics():
    snap = metrics.snapshot()
    snap["strategy"] = CACHE_STRATEGY
    return snap


@app.get("/items/{item_id}")
async def get_item(item_id: int):
    row: Optional[dict] = await strategy.get_item(item_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return row


@app.put("/items/{item_id}")
async def put_item(item_id: int, body: ItemWrite):
    return await strategy.put_item(item_id, body.value)
