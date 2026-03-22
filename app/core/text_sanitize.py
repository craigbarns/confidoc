"""Sanitisation de texte pour PostgreSQL (UTF-8)."""

from __future__ import annotations


def postgres_safe_text(s: str | None) -> str:
    """Retire les octets NUL (\\x00).

    PostgreSQL rejette les séquences UTF-8 contenant 0x00 dans les colonnes text/varchar
    (asyncpg: CharacterNotInRepertoireError). Les PDF / extractions peuvent en contenir.
    """
    if not s:
        return ""
    return s.replace("\x00", "")
