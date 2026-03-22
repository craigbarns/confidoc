"""Le jeu minimal `golden/golden_sets.minimal.json` doit rester conforme au schéma."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[2]


def test_golden_minimal_conforms_to_schema() -> None:
    schema = json.loads((ROOT / "golden" / "golden_schema.json").read_text(encoding="utf-8"))
    instance = json.loads((ROOT / "golden" / "golden_sets.minimal.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=instance, schema=schema)


def test_golden_schema_is_valid_draft07_meta() -> None:
    """Le fichier schéma est lui-même un JSON valide avec $schema draft-07."""
    raw = (ROOT / "golden" / "golden_schema.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    assert data.get("$schema") == "http://json-schema.org/draft-07/schema#"
    assert "golden_sets" in data.get("properties", {})
