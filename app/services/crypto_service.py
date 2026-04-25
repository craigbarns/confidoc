"""ConfiDoc — Encryption service for sensitive data (PII) and mappings.

Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).
Supports field-level encryption for the database.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, TypeVar

from cryptography.fernet import Fernet
from sqlalchemy import String, TypeDecorator
from sqlalchemy.engine import Dialect

from app.config import get_settings

T = TypeVar("T")


def _derive_key(master_key: str, salt: bytes = b"confidoc-default-salt") -> bytes:
    """Derive a 32-byte Fernet key from the master password using PBKDF2."""
    dk = hashlib.pbkdf2_hmac("sha256", master_key.encode(), salt, 100_000)
    return base64.urlsafe_b64encode(dk[:32])


def encrypt_data(data: str | bytes, master_key: str | None = None) -> str:
    """Encrypt a string or bytes using the master key."""
    if master_key is None:
        master_key = get_settings().ENCRYPTION_MASTER_KEY
    
    key = _derive_key(master_key)
    f = Fernet(key)
    
    payload = data if isinstance(data, bytes) else data.encode("utf-8")
    return f.encrypt(payload).decode("ascii")


def decrypt_data(token: str, master_key: str | None = None) -> str:
    """Decrypt a Fernet token back to a string with fallback for cleartext."""
    if not token:
        return ""
    if master_key is None:
        master_key = get_settings().ENCRYPTION_MASTER_KEY
        
    try:
        key = _derive_key(master_key)
        f = Fernet(key)
        payload = f.decrypt(token.encode("ascii"))
        return payload.decode("utf-8")
    except Exception:
        # If it's not a valid Fernet token, assume it's cleartext (migration)
        return token


# ── Backward compatible mapping encryption ─────────────────────────────

def encrypt_mapping(mapping: dict[str, Any], master_key: str) -> str:
    """Encrypt a mapping dict to a Fernet token string."""
    # Use specific salt for mappings to maintain compatibility if needed
    key = _derive_key(master_key, salt=b"confidoc-pseudo-salt")
    f = Fernet(key)
    payload = json.dumps(mapping, ensure_ascii=False).encode("utf-8")
    return f.encrypt(payload).decode("ascii")


def decrypt_mapping(token: str, master_key: str) -> dict[str, Any]:
    """Decrypt a Fernet token back to a mapping dict."""
    key = _derive_key(master_key, salt=b"confidoc-pseudo-salt")
    f = Fernet(key)
    payload = f.decrypt(token.encode("ascii"))
    return json.loads(payload.decode("utf-8"))


# ── SQLAlchemy Type Decorator ──────────────────────────────────────────

class EncryptedString(TypeDecorator):
    """A type which provides transparent encryption for strings."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return encrypt_data(value)

    def process_result_value(self, value: str | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        try:
            return decrypt_data(value)
        except Exception:
            # Fallback for unencrypted data during migration
            return value
