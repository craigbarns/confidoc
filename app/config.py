"""ConfiDoc Backend — Configuration centralisée via pydantic-settings."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    ALLOWED_ORIGINS: Annotated[
        list[str], NoDecode
    ] = ["http://localhost:3000", "http://localhost:5173"]

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
    ALLOWED_EXTENSIONS: Annotated[list[str], NoDecode] = [
        "pdf",
        "png",
        "jpg",
        "jpeg",
        "tiff",
    ]

    @field_validator("APP_ENV", mode="before")
    @classmethod
    def normalize_app_env(cls, value: str) -> str:
        """Tolère plusieurs alias d'environnement courants."""
        if not isinstance(value, str):
            return value

        normalized = value.strip().lower()
        aliases = {
            "prod": "production",
            "production": "production",
            "staging": "staging",
            "stage": "staging",
            "dev": "development",
            "development": "development",
            "local": "development",
        }
        return aliases.get(normalized, normalized)

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: object) -> list[str] | object:
        """Accepte JSON, string unique ou liste séparée par virgules."""
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []

            # Support format JSON string: '["https://a.com","https://b.com"]'
            if raw.startswith("[") and raw.endswith("]"):
                import json

                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except json.JSONDecodeError:
                    pass

            return [item.strip() for item in raw.split(",") if item.strip()]
        return value

    @field_validator("ALLOWED_EXTENSIONS", mode="before")
    @classmethod
    def parse_allowed_extensions(cls, value: object) -> list[str] | object:
        """Accepte liste JSON ou CSV pour simplifier la config Railway."""
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            if raw.startswith("[") and raw.endswith("]"):
                import json

                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        return [str(item).strip().lower() for item in parsed if str(item).strip()]
                except json.JSONDecodeError:
                    pass
            return [item.strip().lower() for item in raw.split(",") if item.strip()]
        return value

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    @property
    def async_database_url(self) -> str:
        """S'assure d'utiliser le driver asyncpg même si on donne un URL classique."""
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql://") and not url.startswith("postgresql+asyncpg://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    """Singleton settings — cached pour performance."""
    return Settings()
