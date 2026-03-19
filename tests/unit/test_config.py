"""ConfiDoc — Tests configuration."""

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
