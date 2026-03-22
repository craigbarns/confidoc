"""Compare les valeurs attendues (golden) aux champs extraits par build_structured_dataset."""

from __future__ import annotations

import math
from typing import Any


def _normalize_scalar(v: Any) -> Any:
    """Aligne exercice 2024 / '2024' / 2024.0 pour comparaison."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if isinstance(v, float) and v.is_integer():
            return int(v)
        return v
    if isinstance(v, str):
        s = v.strip().replace(" ", "")
        if s.isdigit() and len(s) == 4:
            try:
                return int(s)
            except ValueError:
                return v
        return v.strip()
    return v


def _close_numbers(a: Any, b: Any, *, rel_tol: float, abs_tol: float) -> bool:
    na, nb = _normalize_scalar(a), _normalize_scalar(b)
    if na == nb:
        return True
    try:
        fa = float(na)  # type: ignore[arg-type]
        fb = float(nb)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    if math.isnan(fa) or math.isnan(fb):
        return False
    return math.isclose(fa, fb, rel_tol=rel_tol, abs_tol=abs_tol)


def compare_expected_values_to_fields(
    expected_fields: dict[str, Any],
    actual_fields: dict[str, dict[str, Any]],
    *,
    rel_tol: float = 1e-5,
    abs_tol: float = 0.51,
) -> list[str]:
    """
    Compare uniquement les clés présentes dans `expected_fields`.

    Chaque entrée attendue est soit une valeur brute, soit un dict avec clé `value`
    (comme dans golden `expected_api_subset.fields`).

    Retourne une liste de messages d'écart (vide si OK).
    """
    errors: list[str] = []
    for key, ev in expected_fields.items():
        exp_val = ev["value"] if isinstance(ev, dict) and "value" in ev else ev
        actual = actual_fields.get(key)
        if not isinstance(actual, dict):
            errors.append(f"{key}: champ absent côté extraction")
            continue
        got = actual.get("value")

        if exp_val is None and got in (None, "", []):
            continue
        if exp_val is None and got not in (None, "", []):
            errors.append(f"{key}: attendu null, obtenu {got!r}")
            continue

        if isinstance(exp_val, (int, float)) or (
            isinstance(exp_val, str) and exp_val.replace(".", "", 1).replace("-", "", 1).isdigit()
        ):
            if _close_numbers(exp_val, got, rel_tol=rel_tol, abs_tol=abs_tol):
                continue
            errors.append(f"{key}: attendu {exp_val!r}, obtenu {got!r}")
            continue

        ne, ng = _normalize_scalar(exp_val), _normalize_scalar(got)
        if ne == ng:
            continue
        errors.append(f"{key}: attendu {exp_val!r}, obtenu {got!r}")
    return errors
