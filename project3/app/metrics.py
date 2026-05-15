"""Счётчики для отчёта: hit/miss, обращения к БД, flush Write-Back."""
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class Metrics:
    cache_hits: int = 0
    cache_misses: int = 0
    db_reads: int = 0
    db_writes: int = 0
    write_back_dirty: int = 0
    write_back_flushes: int = 0
    write_back_flushed_items: int = 0
    _lock: Lock = field(default_factory=Lock, repr=False)

    def inc(self, name: str, value: int = 1) -> None:
        with self._lock:
            setattr(self, name, getattr(self, name) + value)

    def reset(self) -> None:
        with self._lock:
            for name in (
                "cache_hits",
                "cache_misses",
                "db_reads",
                "db_writes",
                "write_back_dirty",
                "write_back_flushes",
                "write_back_flushed_items",
            ):
                setattr(self, name, 0)

    def snapshot(self) -> dict:
        with self._lock:
            hits, misses = self.cache_hits, self.cache_misses
            total = hits + misses
            hit_rate = (hits / total * 100.0) if total else 0.0
            return {
                "cache_hits": hits,
                "cache_misses": misses,
                "cache_hit_rate_pct": round(hit_rate, 2),
                "db_reads": self.db_reads,
                "db_writes": self.db_writes,
                "db_total": self.db_reads + self.db_writes,
                "write_back_dirty": self.write_back_dirty,
                "write_back_flushes": self.write_back_flushes,
                "write_back_flushed_items": self.write_back_flushed_items,
            }


metrics = Metrics()
