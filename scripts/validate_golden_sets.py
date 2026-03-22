#!/usr/bin/env python3
"""Valide un fichier golden_sets.json contre golden/golden_schema.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Valide golden_sets JSON (JSON Schema).")
    parser.add_argument(
        "json_file",
        nargs="?",
        default=str(root / "golden" / "golden_sets.minimal.json"),
        help="Fichier à valider (défaut: golden/golden_sets.minimal.json)",
    )
    args = parser.parse_args()
    path = Path(args.json_file)
    if not path.is_file():
        print(f"Erreur: fichier introuvable: {path}", file=sys.stderr)
        return 1

    try:
        import jsonschema
    except ImportError:
        print("Erreur: installez les deps dev: pip install -e '.[dev]'", file=sys.stderr)
        return 1

    schema_path = root / "golden" / "golden_schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    instance = json.loads(path.read_text(encoding="utf-8"))

    try:
        jsonschema.validate(instance=instance, schema=schema)
    except jsonschema.ValidationError as e:
        print(f"Validation échouée: {e.message}", file=sys.stderr)
        print(f"  Chemin: {' / '.join(str(p) for p in (e.absolute_path or []))}", file=sys.stderr)
        return 1

    try:
        display = path.relative_to(root)
    except ValueError:
        display = path
    print(f"OK — {display} conforme à golden_schema.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
