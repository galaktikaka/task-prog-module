"""Фабрика: по CACHE_STRATEGY выбирается нужная реализация."""
from config import CACHE_STRATEGY
from strategies.base import CacheStrategy
from strategies.cache_aside import CacheAsideStrategy
from strategies.write_back import WriteBackStrategy
from strategies.write_through import WriteThroughStrategy


def create_strategy() -> CacheStrategy:
    mapping = {
        "cache_aside": CacheAsideStrategy,
        "write_through": WriteThroughStrategy,
        "write_back": WriteBackStrategy,
    }
    cls = mapping.get(CACHE_STRATEGY)
    if cls is None:
        raise ValueError(f"Unknown CACHE_STRATEGY: {CACHE_STRATEGY}")
    return cls()
