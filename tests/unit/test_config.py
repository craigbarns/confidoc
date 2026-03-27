"""ConfiDoc — Tests configuration."""

import warnings

from app.config import Settings, get_settings


def test_settings_defaults():
    """Les settings par défaut sont correctes."""
    settings = get_settings()
    assert settings.APP_NAME == "ConfiDoc"
    assert settings.API_V1_PREFIX == "/api/v1"


def test_settings_max_upload():
    """Le calcul de taille max upload est correct."""
    settings = Settings(MAX_UPLOAD_SIZE_MB=50)
    assert settings.max_upload_size_bytes == 50 * 1024 * 1024


def test_settings_environment_flags():
    """Les flags d'environnement fonctionnent."""
    dev = Settings(APP_ENV="development")
    assert dev.is_development is True
    assert dev.is_production is False

    prod = Settings(APP_ENV="production")
    assert prod.is_production is True
    assert prod.is_development is False


def test_settings_env_aliases():
    """APP_ENV accepts common aliases."""
    assert Settings(APP_ENV="prod").APP_ENV == "production"
    assert Settings(APP_ENV="dev").APP_ENV == "development"
    assert Settings(APP_ENV="stage").APP_ENV == "staging"
    assert Settings(APP_ENV="local").APP_ENV == "development"


def test_settings_async_database_url():
    """Database URL auto-converts to asyncpg driver."""
    s1 = Settings(DATABASE_URL="postgres://user:pass@host/db")
    assert s1.async_database_url.startswith("postgresql+asyncpg://")

    s2 = Settings(DATABASE_URL="postgresql://user:pass@host/db")
    assert s2.async_database_url.startswith("postgresql+asyncpg://")

    s3 = Settings(DATABASE_URL="postgresql+asyncpg://user:pass@host/db")
    assert s3.async_database_url == "postgresql+asyncpg://user:pass@host/db"


def test_production_warns_on_default_secrets():
    """Production mode warns if secrets are not changed."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        Settings(APP_ENV="production", SECRET_KEY="CHANGE-ME")
        security_warnings = [x for x in w if "SECURITY" in str(x.message)]
        assert len(security_warnings) >= 1


def test_development_no_warning():
    """Development mode does not warn on default secrets."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        Settings(APP_ENV="development")
        security_warnings = [x for x in w if "SECURITY" in str(x.message)]
        assert len(security_warnings) == 0


def test_allowed_origins_from_csv():
    """ALLOWED_ORIGINS parses CSV string."""
    s = Settings(ALLOWED_ORIGINS="https://a.com,https://b.com")
    assert s.ALLOWED_ORIGINS == ["https://a.com", "https://b.com"]


def test_allowed_origins_from_json():
    """ALLOWED_ORIGINS parses JSON array string."""
    s = Settings(ALLOWED_ORIGINS='["https://a.com","https://b.com"]')
    assert s.ALLOWED_ORIGINS == ["https://a.com", "https://b.com"]


def test_rate_limit_config_defaults():
    """Rate limiting config has sensible defaults."""
    s = Settings()
    assert s.RATE_LIMIT_LOGIN == "10/minute"
    assert s.RATE_LIMIT_UPLOAD == "30/minute"
    assert s.RATE_LIMIT_DEFAULT == "120/minute"


def test_debug_defaults_to_false():
    """DEBUG defaults to False for safety."""
    s = Settings()
    assert s.DEBUG is False


def test_ocr_config_defaults():
    """OCR configuration has sensible defaults."""
    s = Settings()
    assert s.OCR_DPI == 300
    assert s.OCR_LANG == "fra+eng"
    assert s.OCR_ENGINE == "auto"
    assert s.OCR_PREPROCESSING is True


def test_ocr_dpi_override():
    """OCR_DPI can be overridden."""
    s = Settings(OCR_DPI=600)
    assert s.OCR_DPI == 600


def test_ocr_lang_override():
    """OCR_LANG can be overridden."""
    s = Settings(OCR_LANG="fra")
    assert s.OCR_LANG == "fra"


