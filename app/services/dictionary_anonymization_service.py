"""ConfiDoc — Anonymisation par dictionnaire (règles métier spécifiques).

Remplacement déterministe basé sur des patterns prédéfinis.
Plus fiable que le LLM pour les cas d'usage connus.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logging import get_logger
from app.services.entity_registry import EntityRegistry

logger = get_logger(__name__)

# =============================================================================
# DICTIONNAIRE D'ANONYMISATION
# =============================================================================

# Ordre important: du plus spécifique au plus général

# ⚠ GOVERNANCE: Rules below may contain client-specific patterns.
# In production, prefer loading from ANONYMIZATION_RULES_PATH env var.
def _load_external_rules():
    """Load rules from external JSON file if ANONYMIZATION_RULES_PATH is set."""
    import os, json
    path = os.environ.get("ANONYMIZATION_RULES_PATH", "")
    if not path:
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        return data.get("replacement_rules"), data.get("partial_replacements"), data.get("post_cleanup_rules")
    except Exception:
        return None

_external = _load_external_rules()

REPLACEMENT_RULES = [
    # === ADRESSES COMPLÈTES (en premier pour éviter les collisions) ===
    (r'(?i)41\s+RUE\s+FONGATE\s*\n\s*13006\s+MARSEILLE', '[ADRESSE_SOCIETE_1]', False),
    (r'(?i)41\s+RUE\s+FONGATE', '[ADRESSE_RUE_1]', False),
    (r'(?i)91\s+RUE\s+BRETEUIL\s*\n\s*13006\s+MARSEILLE', '[ADRESSE_CABINET_1]', False),
    (r'(?i)91\s+RUE\s+BRETEUIL', '[ADRESSE_RUE_2]', False),
    (r'12[\s,]*TRAVERSE\s+DU\s+SIPHON[^\n]*\n[^\n]*13012\s+MARSEILLE[^\n]*\n[^\n]*FRANCE', '[ADRESSE_PERSONNE_1]', True),
    (r'12\s+TRAVERSE\s+DU\s+SIPHON\s*\n\s*APT\s+302\s*\n\s*13012\s+MARSEILLE\s*\n\s*FRANCE', '[ADRESSE_SOCIETE_LIEE_1]', True),
    (r'12\s+TRAVERSE\s+DU\s+SIPHON\s*\n\s*13012\s+MARSEILLE\s*\n\s*FRANCE', '[ADRESSE_SOCIETE_LIEE_2]', True),
    (r'5085\s+FAV\s+DE\s+SAINT-MENET\s*\n\s*13011\s+MARSEILLE\s+11EME', '[ADRESSE_LOCAL_1]', True),
    (r'Lot\s+25\s+53\s+52\s+51[^\n]*\n\s*5085\s+FAV\s+DE\s+SAINT-MENET[^\n]*\n\s*13011\s+MARSEILLE\s+11EME', '[ADRESSE_LOCAL_DETAIL_1]', True),
    
    # === PERSONNES (noms complets, prénoms isolés) ===
    (r'(?i)GREGORY\s+BARANES', '[PERSONNE_1]', False),
    (r'(?i)BARANES\s+GR[ÉE]GORY', '[PERSONNE_1]', False),
    (r'(?i)BARANES\s+GREGORY', '[PERSONNE_1]', False),
    (r'(?i)\\bBARANES\\b', '[PERSONNE_1]', False),
    (r'\bGREGORY\b', '[PRENOM_1]', True),  # Prénom seul en majuscule
    (r'\bGr[ée]gory\b', '[PRENOM_1]', False),  # Prénom en casse mixte
    
    # === SOCIÉTÉS LIÉES (ordre: plus spécifique avant) ===
    (r'(?i)WEINVEST\s+III', '[SOCIETE_LIEE_5]', False),
    (r'(?i)WEINVEST\s+II', '[SOCIETE_LIEE_4]', False),
    (r'(?i)WEINVEST\s+I', '[SOCIETE_LIEE_3]', False),
    (r'(?i)WEINVEST', '[SOCIETE_LIEE_2]', False),
    (r'(?i)WEBUILD', '[SOCIETE_LIEE_1]', False),
    
    # === SOCIÉTÉ PRINCIPALE ET VARIANTES OCR ===
    (r'(?i)NEXTCOMPTA', '[CABINET_COMPTABLE_1]', False),
    (r'(?i)WEMADE', '[SOCIETE_1]', False),
    (r'(?i)WEMAD\b', '[SOCIETE_1]', False),
    (r'(?i)WENAGE', '[SOCIETE_1]', False),
    (r'(?i)WENNDE', '[SOCIETE_1]', False),
    (r'(?i)MENADE', '[SOCIETE_1]', False),
    (r'(?i)NOMBDE', '[SOCIETE_1]', False),
    
    # === BANQUES / TIERS ===
    (r'BANQUE\s+SOCI[ÉE]T[ÉE]\s+G[ÉE]N[ÉE]RALE', '[BANQUE_1]', True),
    (r'SOCI[ÉE]T[ÉE]\s+G[ÉE]N[ÉE]RALE', '[BANQUE_1]', True),
    (r'BANQUE\s+REVOLUT', '[BANQUE_2]', True),
    (r'(?i)\bREVOLUT\b', '[BANQUE_2]', False),
    (r'(?i)\bPRADIMO\b', '[TIERS_SOCIETE_1]', False),
    (r'(?i)\bGENERALI\b', '[ASSUREUR_1]', False),
    (r'(?i)\bAXA\b', '[ASSUREUR_2]', False),
    (r'(?i)\bAG2R\b', '[ORGANISME_1]', False),
    
    # === IDENTIFIANTS ===
    (r'832419428', '[SIREN_SOCIETE_1]', False),  # SIREN
    (r'032419428', '[SIREN_SOCIETE_1]', False),  # Variante OCR fréquente
    (r'83241942B', '[SIREN_SOCIETE_1]', False),  # Variante OCR O/B/8
    (r'\[SIRET\]', '[SIRET_SOCIETE_1]', False),  # Déjà tokenisé
    (r'\b\d{3}\s*\d{3}\s*\d{3}\s*\d{5}\b', '[SIRET]', False),  # SIRET générique
    (r'511983496', '[SIREN_TIERS_1]', False),
    (r'1386807824664619B0202562', '[REFERENCE_LOCAL_1]', False),
    (r'138680782466', '[INVARIANT_LOCAL_1]', False),
    
    # === EMPRUNTS / RÉFÉRENCES ===
    (r'221330101477', '[EMPRUNT_1]', False),
    (r'223040100099', '[EMPRUNT_2]', False),
    (r'224086100433', '[EMPRUNT_3]', False),
    (r'224052101277', '[EMPRUNT_4]', False),
    
    # === DONNÉES PERSONNELLES ===
    (r'23/02/1980', '[DATE_NAISSANCE_1]', False),
    (r'TOULOUSE', '[VILLE_NAISSANCE_1]', False),
    # Département de naissance en clair (ex: "N° Département 34")
    (r'(?i)N°\s*D[ée]partement\s+\d{1,3}', 'N° Département [DEPT_NAISSANCE]', False),
    # Ville + arrondissement en clair dans formulaires (ex: MARSEILLE 11EME)
    (r'(?i)\bMARSEILLE\s+\d{1,2}(?:E|ER|EME|ÈME)?\b', '[VILLE]', False),
    (r'(?i)\bMARSEILLE\b', '[VILLE]', False),
    (r'(?i)\bSAINT-MENET\b', '[LIEU_DIT]', False),
    
    # === QUASI-IDENTIFIANTS MÉTIER (marques, logiciels, organismes semi-identifiants) ===
    (r'(?i)\bLOA\s+TESLA\b', 'LOA [MARQUE_VEHICULE]', False),
    (r'(?i)\bTESLA\b', '[MARQUE_VEHICULE]', False),
    (r'(?i)\bTiime\s+Expert\b', '[LOGICIEL_COMPTABLE]', False),
    (r'(?i)\bTiime\b', '[LOGICIEL_COMPTABLE]', False),

    # === EMAILS ===
    (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', False),
    
    # === TÉLÉPHONES ===
    (r'\b(?:\+33|0)\s?[1-9](?:[\s.-]?\d{2}){4}\b', '[TELEPHONE]', False),
    
    # === IBAN ===
    (r'\b[A-Z]{2}\d{2}[\s]?[A-Z0-9]{4}[\s]?(?:[A-Z0-9]{4}[\s]?){2,7}[A-Z0-9]{1,4}\b', '[IBAN]', False),
]

# Remplacements dans les libellés comptables (partiels)
PARTIAL_REPLACEMENTS = [
    # Comptes de personnel — code PCG + nom ou initiales (ex: 421BAR, 455BARANES)
    (r'(?i)421\w*\s+BARANES', '421 [PERSONNE_1]', False),
    (r'(?i)455\w*\s+BARANES', '455 [PERSONNE_1]', False),
    (r'421BAR\b', '421[PERSONNE_1]', True),
    (r'421\w*\s+BAR\s+', '421 [PERSONNE_1] ', True),
    
    # Comptes de sociétés liées  
    (r'451\w*\s+WEBUILD', '451 [SOCIETE_LIEE_1]', True),
    (r'451\w*\s+WEINVEST\s+III', '451 [SOCIETE_LIEE_5]', True),
    (r'451\w*\s+WEINVEST\s+II', '451 [SOCIETE_LIEE_4]', True),
    (r'451\w*\s+WEINVEST\s+I', '451 [SOCIETE_LIEE_3]', True),
    (r'451\w*\s+WEINVEST', '451 [SOCIETE_LIEE_2]', True),
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
        r'[^\n]{0,150}',
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
    (r'\b\d{5}\s+[A-ZÀ-ÿ][A-ZÀ-ÿ\'\-\s]{1,40}\b', '[ADRESSE_VILLE]', False),

    # 4b) Standalone postal codes from known addresses (residual after city replacement)
    (r'\b130(?:06|11|12)\b', '[CODE_POSTAL]', False),

    # 5) Prénom ou nom partiellement visible avant/après token personne
    #    ex: "Gregory [PERSONNE_1]" ou "M [PERSONNE_1]"
    (r'(?i)\b[A-ZÀ-ÿ][A-Za-zÀ-ÿ\'\-]{1,40}\s+\[PERSONNE_\d+\]', '[PERSONNE_1]', False),
    (r'(?i)\[PERSONNE_\d+\]\s+[A-ZÀ-ÿ][A-Za-zÀ-ÿ\'\-]{1,40}\b', '[PERSONNE_1]', False),
    #    ex: "M Nom complet" suivi de "Gregory [PERSONNE_1]"
    (r'(?i)\bM\s+Nom\s+complet\s+\w+\s+\[PERSONNE_\d+\]', 'M Nom complet [PERSONNE_1]', False),

    # 6) Bloc cabinet encore visible autour de son adresse
    (r'(?i)\b(?:SAS\s+)?\[CABINET_COMPTABLE_1\]\b[^\n]{0,100}', '[CABINET_COMPTABLE_1]', False),
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
    entity_counter = {}
    
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
            entity_type = replacement.strip('[]')
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
            
            entity_type = replacement.strip('[]')
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

    # Build EntityRegistry from the hardcoded dictionary
    registry = EntityRegistry()
    # Seed registry with all known mappings from REPLACEMENT_RULES
    _SEED_PAIRS = [
        ("GREGORY BARANES", "[PERSONNE_1]", "PERSONNE"),
        ("BARANES GREGORY", "[PERSONNE_1]", "PERSONNE"),
        ("BARANES", "[PERSONNE_1]", "PERSONNE"),
        ("GREGORY", "[PRENOM_1]", "PRENOM"),
        ("WEMADE", "[SOCIETE_1]", "SOCIETE"),
        ("WEBUILD", "[SOCIETE_LIEE_1]", "SOCIETE_LIEE"),
        ("WEINVEST", "[SOCIETE_LIEE_2]", "SOCIETE_LIEE"),
        ("WEINVEST I", "[SOCIETE_LIEE_3]", "SOCIETE_LIEE"),
        ("WEINVEST II", "[SOCIETE_LIEE_4]", "SOCIETE_LIEE"),
        ("WEINVEST III", "[SOCIETE_LIEE_5]", "SOCIETE_LIEE"),
        ("NEXTCOMPTA", "[CABINET_COMPTABLE_1]", "CABINET_COMPTABLE"),
        ("MARSEILLE", "[VILLE]", "VILLE"),
        ("TOULOUSE", "[VILLE_NAISSANCE_1]", "VILLE"),
        ("TESLA", "[MARQUE_VEHICULE]", "MARQUE"),
        ("TIIME EXPERT", "[LOGICIEL_COMPTABLE]", "LOGICIEL"),
    ]
    for raw_val, placeholder, prefix in _SEED_PAIRS:
        registry.seed(raw_val, placeholder, prefix)

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


async def anonymize_document_dictionary(text: str) -> tuple[str, list[dict], EntityRegistry]:
    """Interface compatible avec l'ancien système.
    
    Returns:
        (anonymized_text, detections_list, entity_registry)
    """
    result = anonymize_with_dictionary(text)
    return result["anonymized_text"], result["entities"], result["registry"]
