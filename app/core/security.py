"""ConfiDoc Backend — Utilitaires de sécurité (Hash, JWT RS256)."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

import bcrypt
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


@lru_cache(maxsize=1)
def get_rsa_keys() -> tuple[Any, Any]:
    """Retrieve or generate RSA keys for RS256."""
    if settings.JWT_PRIVATE_KEY and settings.JWT_PUBLIC_KEY:
        private_key = serialization.load_pem_private_key(
            settings.JWT_PRIVATE_KEY.encode(), password=None
        )
        public_key = serialization.load_pem_public_key(settings.JWT_PUBLIC_KEY.encode())
        return private_key, public_key

    if settings.is_production:
        # Should have been caught by config validator, but double-check
        raise RuntimeError("JWT RSA keys missing in production")

    logger.warning("generating_ephemeral_rsa_keys_dev_only")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Vérifie un mot de passe en clair contre son hash bcrypt."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, AttributeError):
        return False


def get_password_hash(password: str) -> str:
    """Retourne le hash bcrypt du mot de passe avec un round de 12."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def create_access_token(
    subject: str | Any, expires_delta: timedelta | None = None, claims: dict[str, Any] | None = None
) -> str:
    """Crée un JWT access token (RS256 preferred, HS256 fallback)."""
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    # SEC-016: Add jti (JWT ID) for individual revocation support
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "iat": datetime.now(UTC),
        "jti": secrets.token_hex(16),
    }
    if claims:
        to_encode.update(claims)

    if settings.JWT_ALGORITHM.startswith("RS"):
        private_key, _ = get_rsa_keys()
        headers = {"kid": settings.JWT_KID}
        return jwt.encode(to_encode, private_key, algorithm=settings.JWT_ALGORITHM, headers=headers)

    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Décode et valide un JWT."""
    try:
        if settings.JWT_ALGORITHM.startswith("RS"):
            _, public_key = get_rsa_keys()
            return jwt.decode(
                token,
                public_key,
                algorithms=[settings.JWT_ALGORITHM],
            )

        return jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def generate_opaque_token(length: int = 48) -> str:
    """Génère un token opaque aléatoire cryptographiquement sûr."""
    return secrets.token_urlsafe(length)


def hash_token(token: str) -> str:
    """SHA-256 hash for secure token storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
