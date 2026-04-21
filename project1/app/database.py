import logging
import time
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)


def create_db_engine() -> Engine:
    return create_engine(
        settings.database_url,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_timeout=settings.pool_timeout,
        pool_pre_ping=True,
        future=True,
    )


engine = create_db_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


def wait_for_database() -> None:
    for attempt in range(1, settings.db_connect_retries + 1):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            logger.info("База данных готова к подключению")
            return
        except SQLAlchemyError as exc:
            logger.warning(
                "База пока недоступна (попытка %s/%s): %s",
                attempt,
                settings.db_connect_retries,
                exc,
            )
            time.sleep(settings.db_connect_retry_delay_sec)
    raise RuntimeError("Не удалось подключиться к БД за отведенное число попыток")


@contextmanager
def get_session() -> Iterator[Session]:
    # Один контекст = одна сессия. Удобно для сервисных операций и тестов.
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

