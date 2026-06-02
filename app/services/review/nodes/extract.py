"""ConfiDoc Backend — Review Agent Node: Extract."""

import json

from app.services.review import llm
from app.services.review.state import ReviewState, build_docling_context


async def extract_node(state: ReviewState) -> ReviewState:
    text = state["anonymized_text"][:12000]
    doc_type = state.get("doc_type", "autre")
    entity_summary = state.get("entity_summary", {})
    docling_ctx = build_docling_context(state)

    prompt = f"""Tu analyses un document de type: {doc_type}
Entites detectees: {json.dumps(entity_summary, ensure_ascii=False)}
{f"DONNEES STRUCTUREES (tableaux / sections):{chr(10)}{docling_ctx}" if docling_ctx else ""}

Extrais les donnees structurees cles de ce document.

INSTRUCTIONS SPECIFIQUES POUR LES BILANS ET DOCUMENTS COMPTABLES:
- Lis CHAQUE LIGNE du bilan, y compris les sous-lignes (ex: dans l'actif circulant,
  distinguer "Creances clients", "Autres creances", "Disponibilites" etc.)
- Ne fusionne JAMAIS des postes differents. "Autres creances" et "Creances clients"
  sont des postes DISTINCTS avec des montants DIFFERENTS.
- Extrais les montants brut, amortissements ET net pour chaque poste si disponibles.
- Extrais les colonnes N et N-1 quand elles existent.
- Pour chaque montant, indique le libelle EXACT tel qu'il apparait dans le document.

Reponds en JSON strict:
{{
  "parties": ["liste des parties/acteurs mentionnes"],
  "dates_cles": {{"description": "date"}},
  "montants_cles": {{"libelle_exact_du_document": montant_numerique}},
  "postes_bilan": {{
    "actif": {{"libelle_exact": {{"brut": montant, "amort": montant, "net": montant, "net_n1": montant}}}},
    "passif": {{"libelle_exact": {{"montant": montant, "montant_n1": montant}}}}
  }},
  "references": ["numeros de reference, dossier, contrat..."],
  "objet": "objet principal du document",
  "duree": "duree si applicable",
  "conditions_particulieres": ["conditions notables"]
}}

IMPORTANT: le champ "postes_bilan" est OBLIGATOIRE pour les bilans. Lis le document
INTEGRALEMENT pour ne manquer aucun poste.

Texte anonymise:
{text}"""

    raw = await llm.llm_call(
        prompt,
        system="Tu es un expert en extraction de donnees documentaires. Reponds uniquement en JSON.",
    )
    parsed = llm.parse_json(raw)

    return {
        **state,
        "extracted_data": parsed,
        "current_step": "extract",
        "steps_completed": state.get("steps_completed", []) + ["extract"],
    }
