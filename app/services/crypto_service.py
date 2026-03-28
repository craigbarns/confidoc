"""ConfiDoc — Encryption service for pseudonym mappings.

Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).
The key is derived from PSEUDO_MAPPING_KEY via PBKDF2.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet


def _derive_key(master_key: str) -> bytes:
    """Derive a 32-byte Fernet key from the master password."""
    dk = hashlib.pbkdf2_hmac("sha256", master_key.encode(), b"confidoc-pseudo-salt", 100_000)
    return base64.urlsafe_b64encode(dk[:32])


def encrypt_mapping(mapping: dict[str, Any], master_key: str) -> str:
    """Encrypt a mapping dict to a Fernet token string."""
    key = _derive_key(master_key)
    f = Fernet(key)
    payload = json.dumps(mapping, ensure_ascii=False).encode("utf-8")
    return f.encrypt(payload).decode("ascii")


def decrypt_mapping(token: str, master_key: str) -> dict[str, Any]:
    """Decrypt a Fernet token back to a mapping dict."""
    key = _derive_key(master_key)
    f = Fernet(key)
    payload = f.decrypt(token.encode("ascii"))
    return json.loads(payload.decode("utf-8"))
