"""ConfiDoc Backend — Review Agent Node: Findings."""

import json

from app.services.review import llm
from app.services.review.constants import GUARDRAILS
from app.services.review.state import ReviewState, build_docling_context


async def findings_node(state: ReviewState) -> ReviewState:
    doc_type = state.get("doc_type", "autre")
    extracted = state.get("extracted_data", {})
    analysis = state.get("analysis", {})
    text = state["anonymized_text"][:10000]
    docling_ctx = build_docling_context(state)

    prompt = f"""Document de type: {doc_type}
Donnees extraites: {json.dumps(extracted, ensure_ascii=False)[:1500]}
Analyse precedente: {json.dumps(analysis, ensure_ascii=False)[:3000]}
{f"TABLEAUX ET STRUCTURE:{chr(10)}{docling_ctx}" if docling_ctx else ""}

Tu dois produire des constats structures selon EXACTEMENT 4 categories.

CONTEXTE SELON TYPE:
- Courrier, correspondance, contrat, gouvernance, mise en demeure: en categorie B, inclure griefs, reserves ou desaccords exprimes de maniere factuelle; en C, ce qui manque pour repondre; en D, pièces ou sources externes a consulter.
- Bilan, liasse, compte de resultat, piece comptable: rester sur logique comptable (concentrations, coherence, manques de detail).


CATEGORIE A — anomalies_confirmees
Uniquement des erreurs PROUVEES par le document lui-meme:
- total qui ne correspond pas a la somme des composantes
- contradiction chiffree explicite entre deux sections
- ratio mathematiquement impossible
Si tu n'en trouves pas, laisse la liste VIDE. C'est normal et preferable.

CATEGORIE B — points_attention
Observations significatives meritant un examen humain:
- poste anormalement concentre par rapport au total
- evolution inhabituelle d'une periode a l'autre
- niveau d'endettement significatif a documenter
Formulation obligatoire: factuelle, neutre, sans jugement juridique.

CATEGORIE C — informations_manquantes
Donnees absentes du document qui limitent l'analyse:
- ventilation non disponible
- annexe non fournie
- detail d'un poste absent
Ce ne sont PAS des anomalies. Ce sont des limites documentaires.

CATEGORIE D — verifications_recommandees
Hypotheses a valider with des sources EXTERNES (statuts, pieces, client):
- "Verifier la situation de liberation du capital aupres des statuts"
- "Confirmer la nature du poste X aupres du client"
Formulation obligatoire: "Verifier...", "Confirmer...", "Rapprocher..."

{GUARDRAILS}

REGLE DE VERDICT: maximum 2 items par categorie, maximum 6 au total.
Mieux vaut 3 constats solides que 9 constats mediocres.

Pour chaque item, indique:
- "description": formulation factuelle et neutre
- "detail": explication complementaire si utile (sinon null)

Reponds en JSON strict:
{{
  "anomalies_confirmees": [{{"description": "...", "detail": "..."}}],
  "points_attention": [{{"description": "...", "detail": "..."}}],
  "informations_manquantes": [{{"description": "...", "detail": "..."}}],
  "verifications_recommandees": [{{"description": "...", "detail": "..."}}]
}}

Texte pour contexte:
{text}"""

    raw = await llm.llm_call(
        prompt,
        system=(
            "Tu es un reviseur comptable senior with 15 ans d'experience. "
            "Tu es connu pour ta rigueur et ton calme. Tu ne dramatises jamais. "
            "Tu distingues clairement fait prouve, observation, limite documentaire et hypothese. "
            "Tu preferes ne rien dire plutot que de speculer. "
            "Reponds uniquement en JSON."
        ),
    )
    parsed = llm.parse_json(raw)

    findings = {
        "anomalies_confirmees": parsed.get("anomalies_confirmees", []),
        "points_attention": parsed.get("points_attention", []),
        "informations_manquantes": parsed.get("informations_manquantes", []),
        "verifications_recommandees": parsed.get("verifications_recommandees", []),
    }

    return {
        **state,
        "findings": findings,
        "current_step": "findings",
        "steps_completed": state.get("steps_completed", []) + ["findings"],
    }
