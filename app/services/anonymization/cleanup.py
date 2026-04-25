"""ConfiDoc Backend — Post-OCR Cleanup Logic."""

import re

# Common OCR typos in French accounting documents
OCR_FIXES: dict[str, str] = {
    "TELEGÉLISATION": "TÉLÉGESTION",
    "TELEGESTION": "TÉLÉGESTION",
    "TELEBEC": "TÉLÉDEC",
    "TELEDEC": "TÉLÉDEC",
    "DGPIP": "DGFiP",
    "Dérivations": "Déclarations",
    "DERIVATIONS": "DÉCLARATIONS",
    "EXRCICE": "EXERCICE",
    "RESUTLAT": "RÉSULTAT",
    "RESUTAT": "RÉSULTAT",
    "RESULAT": "RÉSULTAT",
    "BIIAN": "BILAN",
    "BLLAN": "BILAN",
    "PASSIE": "PASSIF",
    "PRODUTIS": "PRODUITS",
    "CHAGRES": "CHARGES",
    "CHARCES": "CHARGES",
}


def clean_ocr_artifacts(text: str) -> str:
    """Clean OCR artifacts from anonymized text.

    Fixes:
    1. Broken tokens: [SOCIETE_1]É → [SOCIETE_1]
    2. Duplicate adjacent tokens: [PERSONNE_1] [PERSONNE_1] → [PERSONNE_1]
    3. Excessive blank lines → max 2
    4. Common accounting OCR typos
    5. Orphan brackets from partial replacements
    """
    if not text:
        return text

    # 1. Broken tokens: [TOKEN]TrailingChars → [TOKEN]
    text = re.sub(r"(\[[A-Z_]+\d*\])[A-ZÀ-ÿa-zà-ÿ]{1,3}\b", r"\1", text)

    # 2. Duplicate adjacent tokens (with optional whitespace between)
    text = re.sub(r"(\[[A-Z_]+\d*\])\s*\1", r"\1", text)

    # 3. Excessive blank lines → max 2 consecutive
    text = re.sub(r"\n{4,}", "\n\n\n", text)

    # 4. Fix common OCR typos in accounting terms
    for wrong, correct in OCR_FIXES.items():
        text = text.replace(wrong, correct)

    # 5. Clean orphan closing brackets after tokens
    text = re.sub(r"(\[[A-Z_]+\d*\])\]", r"\1", text)

    # 6. Clean up spaces before punctuation
    text = re.sub(r"\s+([.,;:])", r"\1", text)

    return text
