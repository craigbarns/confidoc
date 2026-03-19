"""ConfiDoc Backend — Configuration centralisée via pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration principale de l'application.

    Chargée depuis les variables d'environnement et/ou le fichier .env.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Application ----
    APP_NAME: str = "ConfiDoc"
    APP_ENV: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "CHANGE-ME"
    LOG_LEVEL: str = "DEBUG"

    # ---- API ----
    API_V1_PREFIX: str = "/api/v1"
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # ---- Database ----
    DATABASE_URL: str = (
        "postgresql+asyncpg://confidoc:confidoc_dev_password@localhost:5432/confidoc"
    )

    # ---- Redis ----
    REDIS_URL: str = "redis://localhost:6379/0"

    # ---- Celery ----
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # ---- MinIO / S3 ----
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "confidoc_minio"
    MINIO_SECRET_KEY: str = "confidoc_minio_secret"
    MINIO_BUCKET: str = "confidoc-documents"
    MINIO_USE_SSL: bool = False

    # ---- JWT ----
    JWT_SECRET_KEY: str = "CHANGE-ME"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ---- Encryption ----
    ENCRYPTION_MASTER_KEY: str = "CHANGE-ME"

    # ---- File Upload ----
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: list[str] = ["pdf", "png", "jpg", "jpeg", "tiff"]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"


@lru_cache
def get_settings() -> Settings:
    """Singleton settings — cached pour performance."""
    return Settings()
