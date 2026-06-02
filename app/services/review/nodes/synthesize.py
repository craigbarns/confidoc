"""ConfiDoc Backend — Review Agent Node: Synthesize."""

import json

from app.services.review import llm
from app.services.review.constants import GUARDRAILS
from app.services.review.state import ReviewState


async def synthesize_node(state: ReviewState) -> ReviewState:
    doc_type = state.get("doc_type", "autre")
    extracted = state.get("extracted_data", {})
    analysis = state.get("analysis", {})
    findings = state.get("findings", {})
    entity_summary = state.get("entity_summary", {})

    n_confirmed = len(findings.get("anomalies_confirmees", []))
    n_attention = len(findings.get("points_attention", []))
    n_missing = len(findings.get("informations_manquantes", []))
    n_verif = len(findings.get("verifications_recommandees", []))

    prompt = f"""Tu produis la SYNTHESE CABINET pour un professionnel (expert-comptable, juriste, DAF).
Le texte est anonymise. Type de document detecte: {doc_type}

Donnees extraites: {json.dumps(extracted, ensure_ascii=False)[:4000]}
Analyse: {json.dumps(analysis, ensure_ascii=False)[:3000]}
Constats structures (4 niveaux):
- Anomalies confirmees: {n_confirmed}
- Points d'attention: {n_attention}
- Informations manquantes: {n_missing}
- Verifications recommandees: {n_verif}
Detail constats: {json.dumps(findings, ensure_ascii=False)[:4000]}
Entites anonymisees: {json.dumps(entity_summary, ensure_ascii=False)}

{GUARDRAILS}

OBJECTIF: sortie en 5 BLOCS METIER pour l'application (pas une landing, une note exploitable).

1) resume_executif: 2 a 4 phrases — enjeu principal, ton du document, ce qu'il faut retenir.
2) demandes_formelles: liste courte des demandes explicites adressees a quelqu'un (audit, pieces, clarification, delai...). Si aucune demande claire: liste vide.
3) pieces_a_verifier: liste des pieces, sources ou verifications a obtenir ou rapprocher (contrat, factures, echanges, validation interne, statuts...). Formulations factuelles.
4) prochaines_actions: liste d'actions concretes pour le cabinet (note interne, relances, preparation de reponse, chronologie...).
5) complement optionnel: pour les documents COMPTABLES (bilan, liasse, compte de resultat), remplir identification et chiffres_cles en texte court. Pour courriers/contrats, peut rester vide ou resumer parties et objet.

REGLE DE VERDICT:
- "favorable": peu de risques residuels, peu de demandes critiques
- "reserve": plusieurs points a traiter ou informations incompletes
- "defavorable": document incoherent ou risques majeurs pour la decision
En cas de doute: "reserve".

Reponds en JSON strict:
{{
  "resume_executif": "...",
  "demandes_formelles": ["...", "..."],
  "pieces_a_verifier": ["...", "..."],
  "prochaines_actions": ["...", "..."],
  "verdict": "favorable|reserve|defavorable",
  "confiance": 0.0-1.0,
  "complement": {{
    "identification": "parties, objet, dates cles si pertinent",
    "chiffres_cles": "montants ou postes cles si document comptable, sinon chaine vide"
  }}
}}"""

    raw = await llm.llm_call(
        prompt,
        system=(
            "Tu es un senior en cabinet comptable ou juridique. Tu structures la reponse pour "
            "un collaborateur presse. Tu ne dramatises pas. Tu ne remplis pas de listes inutiles. "
            "Reponds uniquement en JSON."
        ),
        temperature=0.2,
    )
    parsed = llm.parse_json(raw)
    comp = parsed.get("complement") or {}
    if not isinstance(comp, dict):
        comp = {}

    return {
        **state,
        "review_note": parsed.get("resume_executif", ""),
        "demandes_formelles": [
            str(x) for x in (parsed.get("demandes_formelles") or []) if str(x).strip()
        ][:12],
        "pieces_a_verifier": [
            str(x) for x in (parsed.get("pieces_a_verifier") or []) if str(x).strip()
        ][:12],
        "prochaines_actions": [
            str(x) for x in (parsed.get("prochaines_actions") or []) if str(x).strip()
        ][:12],
        "confidence": float(parsed.get("confiance", 0.5) or 0.5),
        "verdict": parsed.get("verdict", "reserve"),
        "review_complement": {
            "identification": str(comp.get("identification") or "").strip(),
            "chiffres_cles": str(comp.get("chiffres_cles") or "").strip(),
        },
        "sections": {},
        "current_step": "synthesize",
        "steps_completed": state.get("steps_completed", []) + ["synthesize"],
        "error": None,
    }
