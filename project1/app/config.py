import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_host: str = os.getenv("DB_HOST", "db")
    db_port: int = int(os.getenv("DB_PORT", "5432"))
    db_name: str = os.getenv("DB_NAME", "shop_db")
    db_user: str = os.getenv("DB_USER", "shop_user")
    db_password: str = os.getenv("DB_PASSWORD", "shop_password")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    pool_size: int = int(os.getenv("DB_POOL_SIZE", "5"))
    max_overflow: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    pool_timeout: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    db_connect_retries: int = int(os.getenv("DB_CONNECT_RETRIES", "15"))
    db_connect_retry_delay_sec: int = int(os.getenv("DB_CONNECT_RETRY_DELAY_SEC", "2"))

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = Settings()

