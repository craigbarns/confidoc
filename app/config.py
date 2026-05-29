"""ConfiDoc Backend — Configuration centralisée via pydantic-settings."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Sentinel marking an insecure, unconfigured secret. Production startup is blocked
# (see the production validator below) if any real secret still equals it. Defined
# here so other modules can reference it without hardcoding the literal placeholder
# (the CI security check forbids "CHANGE-ME" literals outside this file).
INSECURE_SECRET_PLACEHOLDER = "CHANGE-ME"


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
    APP_VERSION: str = "0.3.0"
    APP_ENV: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False
    SECRET_KEY: str = "CHANGE-ME"
    LOG_LEVEL: str = "INFO"
    DEMO_MODE: bool = True
    DEMO_SEED_ENABLED: bool = True

    # ---- API ----
    API_V1_PREFIX: str = "/api/v1"
    ALLOWED_ORIGINS: Annotated[
        list[str], NoDecode
    ] = ["http://localhost:3000", "http://localhost:5173"]

    # ---- Database ----
    DATABASE_URL: str = (
        "postgresql+asyncpg://confidoc:confidoc_dev_password@localhost:5432/confidoc"
    )
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 30

    # ---- Redis ----
    REDIS_URL: str = "redis://localhost:6379/0"

    # ---- Celery ----
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    # User-facing document processing. Keep API as the default for single-service
    # Railway deployments; set to "celery" only when dedicated OCR/NLP workers
    # are deployed and consuming the expected queues.
    DOCUMENT_PROCESSING_BACKEND: Literal["api", "celery"] = "api"

    # ---- MinIO / S3 ----
    STORAGE_BACKEND: Literal["local", "minio", "database"] = "local"
    LOCAL_UPLOAD_DIR: str = "/tmp/confidoc_uploads"
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "confidoc_minio"
    MINIO_SECRET_KEY: str = "confidoc_minio_secret"
    MINIO_BUCKET: str = "confidoc-documents"
    MINIO_USE_SSL: bool = False

    # ---- JWT ----
    JWT_SECRET_KEY: str = "CHANGE-ME"
    JWT_PRIVATE_KEY: str | None = None
    JWT_PUBLIC_KEY: str | None = None
    JWT_KID: str = "confidoc-default-v1"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ---- Encryption ----
    ENCRYPTION_MASTER_KEY: str = "CHANGE-ME"
    # Key for encrypting the reversible pseudonymization mapping (Fernet)
    PSEUDO_MAPPING_KEY: str = "CHANGE-ME"

    # ---- RGPD Retention (days, 0 = no auto-purge) ----
    RETENTION_RAW_FILE_DAYS: int = 90
    RETENTION_OCR_TEXT_DAYS: int = 180
    RETENTION_ENTITIES_DAYS: int = 365
    RETENTION_AUDIT_LOGS_DAYS: int = 1095  # 3 years
    RETENTION_EXPORTS_DAYS: int = 30
    RETENTION_MAPPING_DAYS: int = 90

    # ---- File Upload ----
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: Annotated[list[str], NoDecode] = [
        "pdf",
        "png",
        "jpg",
        "jpeg",
        "tiff",
    ]

    # PDF extraction (PyMuPDF / OCR)
    # Insère des marqueurs ---PAGE N--- entre les pages (extraction native et OCR).
    PDF_PAGE_MARKERS: bool = True

    # ---- OCR Engine Tuning ----
    # DPI for pdf2image conversion (higher = better accuracy but slower). 300 is standard.
    OCR_DPI: int = 300
    # Tesseract language(s). "fra+eng" detects both French and English text.
    OCR_LANG: str = "fra+eng"
    # OCR engine strategy for scan fallback: auto|tesseract|doctr.
    OCR_ENGINE: Literal["auto", "tesseract", "doctr"] = "auto"
    # Enable image preprocessing (deskew, denoise, contrast, binarize) before OCR.
    OCR_PREPROCESSING: bool = True

    # Webhook optionnel après validation humaine (POST JSON {event, document_id}).
    WEBHOOK_ON_VALIDATE_URL: str = ""
    WEBHOOK_ON_VALIDATE_SECRET: str = ""

    # ---- LLM Assistive (V2) ----
    # Vise uniquement les suggestions de spans (pas d'automatisation définitive).
    # Note: le nom "LLM" est conservé par compatibilité, mais on peut provider NER aussi.
    LLM_ASSISTIVE_ENABLED: bool = False
    LLM_PROVIDER: Literal["mistral", "huggingface", "presidio"] = "mistral"
    # Secrets: à fournir via Railway Secrets / variables d'environnement.
    MISTRAL_API_KEY: str = ""
    MISTRAL_BASE_URL: str = "https://api.mistral.ai"
    MISTRAL_MODEL: str = "mistral-large-latest"
    MISTRAL_ENABLED: bool = False
    MISTRAL_TIMEOUT_SECONDS: int = 180

    # Hugging Face NER assistif (API gérée en UE)
    HF_API_KEY: str = ""
    HF_INFERENCE_URL: str = ""  # ex: https://<endpoint>.endpoints.huggingface.cloud or https://api-inference.huggingface.co/models/<model>
    HF_MODEL: str = "ner-fr-assist"
    HF_TASK: str = "ner"

    # Contraintes RGPD / minimisation
    SENSITIVE_CLIENT_MODE: bool = False
    LLM_MIN_DETECTIONS: int = 2
    LLM_CONFIDENCE_THRESHOLD: float = 0.75
    LLM_MAX_SNIPPETS: int = 3
    LLM_SNIPPET_CHARS: int = 800
    # Augmenté de 6 000 → 20 000 chars pour couvrir des bilans/actes de plusieurs pages.
    # Pour les documents dépassant cette limite, le service doit chunker avant appel LLM.
    LLM_MAX_DOC_CHARS: int = 20000

    # ---- Local AI (Ollama / Open WebUI stack) ----
    OLLAMA_ENABLED: bool = False
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3:1.7b"
    OLLAMA_TIMEOUT_SECONDS: int = 90
    ADMIN_RECOVERY_TOKEN: str = ""

    # ---- Bootstrap & setup ----
    # Requis en production pour appeler POST /auth/bootstrap-admin.
    BOOTSTRAP_SECRET: str = ""

    # ---- Email (password reset, notifications) ----
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@confidoc.fr"
    SMTP_TLS: bool = True
    # Recipient for public beta access requests. Falls back to SMTP_FROM if empty.
    BETA_LEAD_RECIPIENT_EMAIL: str = ""
    # URL de base de l'interface (ex: https://app.confidoc.fr) pour les liens de reset.
    APP_BASE_URL: str = "http://localhost:3000"
    # Durée de validité du token de reset (en minutes)
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30

    # ---- Structured extraction thresholds (optional overrides) ----
    EXTRACT_AMOUNT_MIN_DEFAULT: float | None = None
    EXTRACT_AMOUNT_MIN_LOW: float | None = None
    EXTRACT_AMOUNT_ABS_HARD_CAP: float | None = None
    EXTRACT_COMPONENT_ABS_HARD_CAP: float | None = None
    EXTRACT_COMPONENT_VS_PASSIF_RATIO_CAP: float | None = None
    EXTRACT_QUALITY_READY_COVERAGE_MIN: float | None = None
    EXTRACT_QUALITY_READY_CONSISTENCY_MIN: float | None = None
    EXTRACT_QUALITY_CORE_NUMERIC_MIN: float | None = None
    EXTRACT_QUALITY_CORE_AGGREGATE_MIN: float | None = None
    EXTRACT_AGGREGATE_REL_TOLERANCE: float | None = None
    EXTRACT_AGGREGATE_ABS_TOLERANCE_MIN: float | None = None

    # ---- Semantic RAG embeddings ----
    # Disabled by default: the default BGE-M3 model is several GB and should not
    # be downloaded implicitly during local demos or constrained deployments.
    RAG_EMBEDDINGS_ENABLED: bool = False
    RAG_EMBED_MODEL: str = "BAAI/bge-m3"

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

    # ---- Rate Limiting ----
    RATE_LIMIT_LOGIN: str = "10/minute"
    RATE_LIMIT_UPLOAD: str = "30/minute"
    RATE_LIMIT_DEFAULT: str = "120/minute"

    @staticmethod
    def _is_insecure_secret(value: str | None) -> bool:
        """Return True for default, placeholder or too-short production secrets."""
        normalized = (value or "").strip()
        if not normalized:
            return True
        if "CHANGE-ME" in normalized.upper():
            return True
        return len(normalized.encode("utf-8")) < 32

    @model_validator(mode="after")
    def _block_insecure_defaults(self) -> "Settings":
        """Block startup when production runs with default secrets."""
        if self.APP_ENV == "production":
            insecure = []
            for key in (
                "SECRET_KEY",
                "JWT_SECRET_KEY",
                "ENCRYPTION_MASTER_KEY",
                "PSEUDO_MAPPING_KEY",
            ):
                if self._is_insecure_secret(getattr(self, key)):
                    insecure.append(key)

            if self.JWT_ALGORITHM.startswith("RS") and (
                not self.JWT_PRIVATE_KEY or not self.JWT_PUBLIC_KEY
            ):
                insecure.append("JWT_PRIVATE_KEY/JWT_PUBLIC_KEY")
            if insecure:
                from app.core.logging import get_logger
                get_logger("config").error("production_blocked_insecure_config", missing=insecure)
                raise ValueError(
                    f"Production blocked: insecure default values found for: "
                    f"{', '.join(insecure)}. Set these via environment variables!"
                )
            if self.STORAGE_BACKEND == "local":
                raise ValueError(
                    "Production blocked: STORAGE_BACKEND=local is ephemeral. "
                    "Use minio/S3 or database-backed storage."
                )
        return self

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
