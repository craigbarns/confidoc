"""ConfiDoc — Anonymisation par dictionnaire gouverné.

Remplacement déterministe basé sur des patterns prédéfinis.
Plus fiable que le LLM pour les cas d'usage connus.

Les règles embarquées doivent rester génériques. Les dictionnaires client,
noms propres et cas de démonstration se chargent via ANONYMIZATION_RULES_PATH.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from app.core.logging import get_logger
from app.services.entity_registry import EntityRegistry

logger = get_logger(__name__)

# =============================================================================
# DICTIONNAIRE D'ANONYMISATION
# =============================================================================

# Ordre important: du plus spécifique au plus général.
Rule = tuple[str, str, bool]
ExternalRules = tuple[Any, Any, Any]


def _load_external_rules() -> ExternalRules | None:
    """Load rules from external JSON file if ANONYMIZATION_RULES_PATH is set."""
    path = os.environ.get("ANONYMIZATION_RULES_PATH", "")
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return (
            data.get("replacement_rules"),
            data.get("partial_replacements"),
            data.get("post_cleanup_rules"),
        )
    except Exception as exc:
        logger.warning(
            "anonymization_external_rules_load_failed",
            path=path,
            error=str(exc),
        )
        return None

_external = _load_external_rules()

REPLACEMENT_RULES: list[Rule] = [
    # === VALEURS LIBELLEES ===
    (
        r'(?im)^((?:nom|pr[ée]nom|contact|dirigeant|g[ée]rant|titulaire|b[ée]n[ée]ficiaire)'
        r'\s*[:\-]\s*)[^\n;]{2,100}$',
        r'\1[PERSONNE]',
        True,
    ),
    (
        r'(?im)^((?:client|destinataire|interlocuteur)\s*[:\-]\s*)[^\n;]{2,120}$',
        r'\1[CLIENT]',
        True,
    ),
    (
        r'(?im)^((?:raison\s+sociale|soci[ée]t[ée]|fournisseur|prestataire)'
        r'\s*[:\-]\s*)[^\n;]{2,140}$',
        r'\1[SOCIETE]',
        True,
    ),
    (
        r'(?im)^((?:n[°o]\s*(?:client|compte|dossier|contrat)|num[ée]ro\s+(?:client|compte|dossier|contrat))'
        r'\s*[:\-]?\s*)[A-Z0-9][A-Z0-9\-_/]{2,40}$',
        r'\1[ID]',
        True,
    ),

    # === IDENTIFIANTS GENERIQUES ===
    (
        r'\b[A-Z]{2}\d{2}[\s]?[A-Z0-9]{4}[\s]?'
        r'(?:[A-Z0-9]{4}[\s]?){2,7}[A-Z0-9]{1,4}\b',
        '[IBAN]',
        False,
    ),
    (r'(?i)\bFR\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{3}\b', '[TVA]', False),
    (r'\[SIRET\]', '[SIRET_SOCIETE_1]', False),  # Deja tokenise
    (r'\b\d{3}\s*\d{3}\s*\d{3}\s*\d{5}\b', '[SIRET]', False),  # SIRET generique
    (r'\b\d{9}\b', '[SIREN]', False),
    (r'\b[12]\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{2}\b', '[NIR]', False),
    (r'(?im)\b(BIC\s*[:\-]?\s*)[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b', r'\1[BIC]', True),
    (
        r'(?im)\b((?:date\s+de\s+naissance|n[ée]e?\s+le)\s*[:\-]?\s*)'
        r'\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}\b',
        r'\1[DATE_NAISSANCE]',
        True,
    ),

    # === SOCIETES / TIERS GENERIQUES ===
    (
        r'(?i)\b(?:SASU?|SARL|EURL|SCI|SA|SNC|SELARL|SCP|Association|GIE|EI|EIRL)\s+'
        r'[A-Z0-9][A-Z0-9À-ÿ &\'’.\-]{1,80}\b',
        '[SOCIETE]',
        False,
    ),
    (
        r'(?i)\b[A-Z0-9][A-Z0-9À-ÿ &\'’.\-]{1,80}\s+'
        r'(?:SASU?|SARL|EURL|SCI|SA|SNC|SELARL|SCP|Association|GIE|EI|EIRL)\b',
        '[SOCIETE]',
        False,
    ),

    # === ADRESSES / LOCALISATION ===
    (
        r'(?i)\b\d{1,4}\s*[,.]?\s*(?:bis|ter)?\s*'
        r'(?:rue|avenue|av\.?|bd\.?|boulevard|impasse|all[ée]e|chemin|traverse|'
        r'faubourg|cours|voie|route|place|passage)\b[^\n.;]{0,150}',
        '[ADRESSE]',
        False,
    ),
    (r'\b\d{5}\s+(?!(?:EUR|EUROS?)\b)[A-ZÀ-ÿ][A-ZÀ-ÿ\'\-\s]{1,40}\b', '[ADRESSE_VILLE]', False),

    # === PERSONNES ===
    (
        r'(?i)\b(?:M|Mme|Madame|Monsieur|Dr|Me)\.?\s+'
        r'[A-ZÀ-ÿ][A-Za-zÀ-ÿ\'\-]{1,40}(?:\s+[A-ZÀ-ÿ][A-Za-zÀ-ÿ\'\-]{1,40}){0,2}\b',
        '[PERSONNE]',
        False,
    ),
    (
        r'(?m)^(?!(?:COMPTE|CHIFFRE|RESULTAT|R[ÉE]SULTAT|TOTAL|BILAN|ACTIF|PASSIF|'
        r'GRAND|LIVRE|BALANCE|JOURNAL|EXERCICE|PERIODE|P[ÉE]RIODE)\b)'
        r'[A-ZÀ-Ÿ][A-ZÀ-Ÿ\'\-]{2,40}(?:\s+[A-ZÀ-Ÿ][A-ZÀ-Ÿ\'\-]{2,40}){1,3}$',
        '[PERSONNE]',
        True,
    ),

    # === BANQUES / TIERS COURANTS ===
    (r'BANQUE\s+SOCI[ÉE]T[ÉE]\s+G[ÉE]N[ÉE]RALE', '[BANQUE_1]', True),
    (r'SOCI[ÉE]T[ÉE]\s+G[ÉE]N[ÉE]RALE', '[BANQUE_1]', True),
    (r'BANQUE\s+REVOLUT', '[BANQUE_2]', True),
    (r'(?i)\bREVOLUT\b', '[BANQUE_2]', False),
    (r'(?i)\bPRADIMO\b', '[TIERS_SOCIETE_1]', False),
    (r'(?i)\bGENERALI\b', '[ASSUREUR_1]', False),
    (r'(?i)\bAXA\b', '[ASSUREUR_2]', False),
    (r'(?i)\bAG2R\b', '[ORGANISME_1]', False),

    # === DONNEES PERSONNELLES ===
    (r'(?i)N°\s*D[ée]partement\s+\d{1,3}', 'N° Département [DEPT_NAISSANCE]', False),
    (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', False),
    (r'\b(?:\+33|0)\s?[1-9](?:[\s.-]?\d{2}){4}\b', '[TELEPHONE]', False),
]

# Remplacements dans les libellés comptables (partiels)
PARTIAL_REPLACEMENTS: list[Rule] = [
    (r'(?i)\b421\w*\s+[A-ZÀ-Ÿ][A-ZÀ-Ÿ\'\-]{2,40}(?:\s+[A-ZÀ-Ÿ][A-ZÀ-Ÿ\'\-]{2,40}){0,3}\b', '421 [PERSONNE]', False),
    (r'(?i)\b455\w*\s+[A-ZÀ-Ÿ][A-ZÀ-Ÿ\'\-]{2,40}(?:\s+[A-ZÀ-Ÿ][A-ZÀ-Ÿ\'\-]{2,40}){0,3}\b', '455 [PERSONNE]', False),
    (r'(?i)\b451\w*\s+[A-Z0-9][A-Z0-9À-ÿ &\'’.\-]{2,80}\b', '451 [SOCIETE]', False),
    (r'(?i)\b512\w*\s+(?:QONTO|REVOLUT|BNP|BRED|LCL|CIC|CAISSE\s+D[\'’]EPARGNE|CR[ÉE]DIT\s+AGRICOLE)\b', '512 [BANQUE]', False),
]

# Nettoyage RGPD final: éliminer les fuites résiduelles après remplacements principaux.
POST_CLEANUP_RULES = [
    # 1) SIRET partiel du type "Siret [SIREN_SOCIETE_1]00038"
    (r'(?i)\bSiret\s+\[SIREN_SOCIETE_1\]\s*\d{3,6}\b', 'Siret [SIRET_SOCIETE_1]', False),
    (r'\[SIREN_SOCIETE_1\]\s*\d{3,6}', '[SIRET_SOCIETE_1]', False),

    # 2) Codes comptables PCG (ex: 2135xx, 6011xx). Ne sont PAS des identifiants d'entreprise.
    #    On les remplace par [CODE_COMPTABLE] au lieu de [IDENTIFIANT_ENTREPRISE].
    (r'\b[0-9OIlSB]{8,14}[A-Z]?\b', '[CODE_COMPTABLE]', False),

    # 3) Adresses ligne voie génériques (élargi: traverse, bat, appt, lot, etc.)
    (
        r'(?i)\b\d{1,4}\s*[,.]?\s*(?:bis|ter)?\s*'
        r'(?:rue|avenue|av\.?|bd\.?|boulevard|impasse|all[ée]e|chemin|traverse|faubourg|cours|voie|fav|route|place|passage)\b'
        r'[^\n.;]{0,150}',
        '[ADRESSE]',
        False,
    ),
    # 3b) Adresses avec "Bat / Bât / appt / apt / étage" (format atypique sans nom de voie)
    (
        r'(?i)(?:Bat|Bât|B[aâ]timent)\s+[A-Z0-9]+\s*[-–,]?\s*(?:appt?|apt|[ée]tage|entr[ée]e)\s*\d*[^\n]{0,80}',
        '[ADRESSE]',
        False,
    ),
    # 3c) "Lot XX XX XX" (références cadastrales/foncières dans DECLOYER)
    (r'(?i)\bLot\s+\d[\d\s]{2,20}[-–]?\s*(?:Bât|Bat|B[aâ]timent)?[^\n]{0,100}', '[ADRESSE]', False),

    # 4) CP + ville (5 chiffres + mot majuscule)
    (r'\b\d{5}\s+(?!(?:EUR|EUROS?)\b)[A-ZÀ-ÿ][A-ZÀ-ÿ\'\-\s]{1,40}\b', '[ADRESSE_VILLE]', False),

    # 4b) Standalone postal code only when explicitly labelled.
    (r'(?i)\b((?:code\s*postal|cp)\s*[:\-]?\s*)\d{5}\b', r'\1[CODE_POSTAL]', False),

    # 4c) Birth place that remains after a labelled birth date.
    (r'(?i)(\[DATE_NAISSANCE\]\s+[àa]\s+)[A-ZÀ-ÿ][A-Za-zÀ-ÿ\'\-\s]{1,40}', r'\1[VILLE]', False),

    # 5) Prénom ou nom partiellement visible avant/après token personne
    #    ex: "Gregory [PERSONNE_1]" ou "M [PERSONNE_1]"
    (r'(?i)\b[A-ZÀ-ÿ][A-Za-zÀ-ÿ\'\-]{1,40}\s+\[PERSONNE_\d+\]', '[PERSONNE_1]', False),
    (r'(?i)\[PERSONNE_\d+\]\s+[A-ZÀ-ÿ][A-Za-zÀ-ÿ\'\-]{1,40}\b', '[PERSONNE_1]', False),
    #    ex: "M Nom complet" suivi de "Gregory [PERSONNE_1]"
    (r'(?i)\bM\s+Nom\s+complet\s+\w+\s+\[PERSONNE_\d+\]', 'M Nom complet [PERSONNE_1]', False),

]


def _normalize_ocr_identifiers(text: str) -> str:
    """Normalise les variantes OCR dans les identifiants avant matching."""
    # Map OCR ambiguities only in long alnum runs likely to be identifiers.
    def _fix(match: re.Match[str]) -> str:
        s = match.group(0)
        return (
            s.replace("O", "0")
            .replace("I", "1")
            .replace("l", "1")
            .replace("S", "5")
            .replace("B", "8")
        )

    return re.sub(r'\b[0-9OIlSB]{8,20}\b', _fix, text)


def _count_occurrences(pattern: str, text: str, case_sensitive: bool = True) -> int:
    """Compte les occurrences d'un pattern."""
    flags = 0 if case_sensitive else re.IGNORECASE
    return len(re.findall(pattern, text, flags | re.MULTILINE))


def _entity_type_from_replacement(replacement: str) -> str:
    """Extract the semantic token from a replacement string."""
    placeholder_match = re.search(r"\[([A-Z0-9_]+)\]", replacement)
    if placeholder_match:
        return placeholder_match.group(1)
    return replacement.strip("[]") or "unknown"



if _external:
    if _external[0] is not None:
        REPLACEMENT_RULES = _external[0]
    if _external[1] is not None:
        PARTIAL_REPLACEMENTS = _external[1]
    if _external[2] is not None:
        POST_CLEANUP_RULES = _external[2]

def anonymize_with_dictionary(text: str) -> dict[str, Any]:
    """Anonymise un texte en utilisant le dictionnaire de règles.

    Returns:
        {
            "anonymized_text": "texte avec tokens",
            "entities": [...],
            "confidence": "high",
            "count": N,
            "method": "dictionary"
        }
    """
    if not text:
        return {
            "anonymized_text": "",
            "entities": [],
            "confidence": "high",
            "count": 0,
            "method": "dictionary",
            "registry": EntityRegistry(),
        }

    entities = []
    # Pré-normalisation OCR pour mieux attraper les SIREN/SIRET dégradés.
    result = _normalize_ocr_identifiers(text)
    entity_counter: dict[str, int] = {}

    # === ÉTAPE 1: Remplacements complets ===
    for pattern, replacement, case_sensitive in REPLACEMENT_RULES:
        flags = 0 if case_sensitive else re.IGNORECASE

        # Trouve toutes les occurrences avant remplacement
        matches = list(re.finditer(pattern, result, flags | re.MULTILINE))

        for match in matches:
            original = match.group(0)
            start = match.start()
            end = match.end()

            # Compteur unique par type d'entité
            entity_type = _entity_type_from_replacement(replacement)
            entity_counter[entity_type] = entity_counter.get(entity_type, 0) + 1

            entities.append({
                "entity_type": entity_type,
                "start_index": start,
                "end_index": end,
                "value_excerpt": original[:100],
                "replacement": replacement,
                "confidence": 0.95
            })

        # Remplace tout
        result = re.sub(pattern, replacement, result, flags=flags | re.MULTILINE)

    # === ÉTAPE 2: Remplacements partiels (libellés comptables) ===
    for pattern, replacement, case_sensitive in PARTIAL_REPLACEMENTS:
        flags = 0 if case_sensitive else re.IGNORECASE

        matches = list(re.finditer(pattern, result, flags | re.MULTILINE))

        for match in matches:
            original = match.group(0)
            start = match.start()
            end = match.end()

            entity_type = _entity_type_from_replacement(replacement)
            entity_counter[entity_type] = entity_counter.get(entity_type, 0) + 1

            entities.append({
                "entity_type": entity_type + "_partiel",
                "start_index": start,
                "end_index": end,
                "value_excerpt": original[:100],
                "replacement": replacement,
                "confidence": 0.90
            })

        result = re.sub(pattern, replacement, result, flags=flags | re.MULTILINE)

    # === ÉTAPE 3: Nettoyage résiduel RGPD (fuites partielles) ===
    for pattern, replacement, case_sensitive in POST_CLEANUP_RULES:
        flags = 0 if case_sensitive else re.IGNORECASE
        result = re.sub(pattern, replacement, result, flags=flags | re.MULTILINE)

    logger.info(
        "dictionary_anonymization_complete",
        detections=len(entities),
        unique_types=len(entity_counter)
    )

    # Build EntityRegistry from actual detections. Client-specific mappings
    # must come from external dictionaries, not from source code.
    registry = EntityRegistry()
    for entity in entities:
        raw_val = str(entity.get("value_excerpt", ""))
        replacement = str(entity.get("replacement", ""))
        placeholder_match = re.search(r"\[([A-Z0-9_]+)\]", replacement)
        if raw_val and placeholder_match:
            prefix = placeholder_match.group(1).split("_", 1)[0]
            registry.seed(raw_val, placeholder_match.group(0), prefix)

    # Apply post-OCR cleanup
    from app.services.anonymization_service import clean_ocr_artifacts
    result = clean_ocr_artifacts(result)

    return {
        "anonymized_text": result,
        "entities": entities,
        "confidence": "high",
        "count": len(entities),
        "method": "dictionary",
        "registry": registry,
    }


async def anonymize_document_dictionary(
    text: str,
) -> tuple[str, list[dict[str, Any]], EntityRegistry]:
    """Interface compatible avec l'ancien système.

    Returns:
        (anonymized_text, detections_list, entity_registry)
    """
    result = anonymize_with_dictionary(text)
    return result["anonymized_text"], result["entities"], result["registry"]
