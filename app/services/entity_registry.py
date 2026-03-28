"""ConfiDoc — EntityRegistry: registre centralisé des entités anonymisées.

Garantit qu'une même valeur reçoit toujours le même placeholder
au sein d'un document (et optionnellement entre documents d'un même lot).

Usage:
    registry = EntityRegistry()
    token = registry.get_or_create("BARANES GREGORY", "PERSONNE")
    # → "[PERSONNE_1]"
    token2 = registry.get_or_create("BARANES GREGORY", "PERSONNE")
    # → "[PERSONNE_1]"  (même valeur = même token)
    token3 = registry.get_or_create("DUPONT JEAN", "PERSONNE")
    # → "[PERSONNE_2]"  (nouvelle valeur = nouveau token)
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


class EntityRegistry:
    """Mapping stable valeur normalisée → placeholder pour un document entier.

    Règle d'or: même valeur brute = même placeholder, quelle que soit
    la position dans le document ou le nombre d'occurrences.
    """

    def __init__(self) -> None:
        # normalized_key → placeholder string (ex: "[PERSONNE_1]")
        self._map: dict[str, str] = {}
        # prefix → running counter
        self._counters: dict[str, int] = {}
        # record all raw values mapped to each placeholder (for audit)
        self._raw_values: dict[str, list[str]] = {}

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def get_or_create(self, raw_value: str, prefix: str) -> str:
        """Return the stable placeholder for *raw_value* under *prefix*.

        If the value was already seen (after normalization), returns the
        same placeholder.  Otherwise allocates a new one.

        Args:
            raw_value: the literal string extracted from the document
            prefix:    semantic category (PERSONNE, SOCIETE, ADRESSE …)

        Returns:
            Placeholder string like ``[PERSONNE_1]``
        """
        if not raw_value or not raw_value.strip():
            return f"[{prefix}]"

        key = self._normalize(raw_value)

        # Fuzzy-match: also check if a very similar key already exists
        # (handles OCR variants like "BARANES" vs "BARANES ")
        if key not in self._map:
            similar = self._find_similar(key, prefix)
            if similar:
                key = similar

        if key not in self._map:
            self._counters[prefix] = self._counters.get(prefix, 0) + 1
            placeholder = f"[{prefix}_{self._counters[prefix]}]"
            self._map[key] = placeholder
            self._raw_values[placeholder] = [raw_value]
        else:
            placeholder = self._map[key]
            if raw_value not in self._raw_values.get(placeholder, []):
                self._raw_values.setdefault(placeholder, []).append(raw_value)

        return placeholder

    def lookup(self, raw_value: str) -> str | None:
        """Return the placeholder if the value was already registered, else None."""
        key = self._normalize(raw_value)
        return self._map.get(key)

    def seed(self, raw_value: str, placeholder: str, prefix: str) -> None:
        """Pre-register a known mapping (e.g. from a client dictionary).

        This allows the dictionary service to seed the registry so that
        the regex-based service uses the same placeholders.
        """
        key = self._normalize(raw_value)
        self._map[key] = placeholder
        self._raw_values.setdefault(placeholder, []).append(raw_value)
        # Update counter so new allocations don't collide
        try:
            num = int(placeholder.strip("[]").rsplit("_", 1)[-1])
            self._counters[prefix] = max(self._counters.get(prefix, 0), num)
        except (ValueError, IndexError):
            pass

    def export_dictionary(self) -> dict[str, str]:
        """Export the normalisedValue → placeholder mapping (for debug/audit)."""
        return dict(self._map)

    def export_raw_mapping(self) -> dict[str, list[str]]:
        """Export placeholder → list[raw_values] mapping."""
        return dict(self._raw_values)

    def export_entity_summary(self) -> dict[str, int]:
        """Count of entities per prefix (e.g. {"PERSONNE": 3, "SOCIETE": 2})."""
        return dict(self._counters)

    @property
    def total_entities(self) -> int:
        return len(self._map)

    # ──────────────────────────────────────────────────────────────────
    # Internals
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize(value: str) -> str:
        """Normalize a raw value to a stable lookup key.

        Pipeline: NFKD → strip accents → upper → collapse whitespace → strip
        """
        txt = unicodedata.normalize("NFKD", value)
        txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
        txt = re.sub(r"\s+", " ", txt.strip().upper())
        # Remove trailing punctuation that OCR might add
        txt = txt.strip(".,;:!?()[]{}\"'")
        return txt

    def _find_similar(self, key: str, prefix: str) -> str | None:
        """Fuzzy-match against existing keys for the same prefix.

        Handles common OCR variations:
        - trailing/leading characters
        - one-char differences for short strings
        """
        if len(key) < 4:
            return None

        for existing_key, placeholder in self._map.items():
            # Only compare within same prefix
            if not placeholder.startswith(f"[{prefix}_"):
                continue

            # Substring containment (one contains the other)
            if key in existing_key or existing_key in key:
                # Only if the shorter is at least 70% of the longer
                ratio = min(len(key), len(existing_key)) / max(len(key), len(existing_key))
                if ratio >= 0.7:
                    return existing_key

        return None
