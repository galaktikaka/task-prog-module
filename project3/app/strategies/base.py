"""Базовый интерфейс стратегии — все три реализации его наследуют."""
from abc import ABC, abstractmethod
from typing import Optional


class CacheStrategy(ABC):
    @abstractmethod
    async def get_item(self, item_id: int) -> Optional[dict]:
        raise NotImplementedError

    @abstractmethod
    async def put_item(self, item_id: int, value: str) -> dict:
        raise NotImplementedError

    async def flush(self) -> dict:
        return {"flushed": 0}
