"""Настройки приложения (читаются из переменных окружения Docker)."""
import os

# cache_aside | write_through | write_back
CACHE_STRATEGY = os.getenv("CACHE_STRATEGY", "cache_aside")
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://bench:bench@localhost:5433/bench"
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6380/0")
# Параметры фоновой записи Write-Back в БД
WRITE_BACK_FLUSH_INTERVAL_SEC = float(os.getenv("WRITE_BACK_FLUSH_INTERVAL_SEC", "2"))
WRITE_BACK_FLUSH_BATCH_SIZE = int(os.getenv("WRITE_BACK_FLUSH_BATCH_SIZE", "50"))
CACHE_TTL_SEC = int(os.getenv("CACHE_TTL_SEC", "300"))
