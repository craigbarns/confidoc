"""ConfiDoc Backend — Visual PDF redaction service."""

import re
import fitz


def redact_pdf_bytes(original_pdf: bytes, sensitive_values: list[str]) -> bytes:
    """Apply visual black redactions on a PDF for provided values."""
    cleaned_values = [v.strip() for v in sensitive_values if v and v.strip()]
    if not cleaned_values:
        return original_pdf

    def normalize(s: str) -> str:
        s = s.replace("\u00a0", " ")
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def candidates_for_value(v: str) -> set[str]:
        """Génère des candidats de recherche robustes.

        Motivations:
        - Les PDF peuvent contenir des espaces/hyphénations différentes de `value_excerpt`.
        - `page.search_for` ne fait pas de regex: on cherche donc des tokens/sous-parties.
        """
        v_norm = normalize(v)
        cands: set[str] = set()
        if not v_norm:
            return cands

        # Cherche la chaîne entière (normalisée) + uppercase
        cands.add(v_norm)
        cands.add(v_norm.upper())

        # Tokens alphanuméric/sous-parties
        tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]{3,}", v_norm)
        for t in tokens:
            # On évite de masquer des tokens trop courts
            if t.isdigit():
                if len(t) >= 4:
                    cands.add(t)
            else:
                if len(t) >= 4:
                    cands.add(t)

        # Cas: valeurs composées, masquer au moins quelques extrémités
        if " " in v_norm:
            parts = [p for p in v_norm.split(" ") if p]
            if len(parts) >= 2:
                cands.add(f"{parts[0]} {parts[1]}")
                cands.add(f"{parts[-2]} {parts[-1]}")

        # Si chaîne alphanumérique, masquer aussi la partie numérique (SIRET/SIREN-like)
        digits = re.sub(r"\D+", "", v_norm)
        if len(digits) >= 5:
            cands.add(digits)

        return cands

    doc = fitz.open(stream=original_pdf, filetype="pdf")
    try:
        for page in doc:
            for value in cleaned_values:
                for cand in candidates_for_value(value):
                    # `search_for` est sensible à la casse; on tente plusieurs variantes.
                    # hit_max évite d'exploser si le token est fréquent.
                    areas = page.search_for(cand)
                    for rect in areas:
                        page.add_redact_annot(rect, fill=(0, 0, 0))
            page.apply_redactions()

        return doc.tobytes(garbage=4, deflate=True)
    finally:
        doc.close()
