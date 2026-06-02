"""ConfiDoc Backend — Review Agent Node: Analyze."""

import json

from app.services.review import llm
from app.services.review.constants import GUARDRAILS
from app.services.review.state import ReviewState, build_docling_context


async def analyze_node(state: ReviewState) -> ReviewState:
    doc_type = state.get("doc_type", "autre")
    extracted = state.get("extracted_data", {})
    text = state["anonymized_text"][:10000]
    docling_ctx = build_docling_context(state)

    prompt = f"""Tu analyses un document de type: {doc_type}
Donnees extraites: {json.dumps(extracted, ensure_ascii=False)[:4000]}
{f"DONNEES STRUCTUREES (tableaux / sections):{chr(10)}{docling_ctx}" if docling_ctx else ""}

Effectue une analyse metier factuelle:
1. Verifie la coherence des montants entre eux
2. Verifie que les elements obligatoires sont presents
3. Evalue la qualite et completude du document
4. Identifie les points d'attention pour un reviseur

{GUARDRAILS}

Reponds en JSON strict:
{{
  "completude": {{"score": 0.0-1.0, "elements_manquants": [...]}},
  "coherence": {{"score": 0.0-1.0, "observations": [...]}},
  "points_attention": ["liste des points a verifier"],
  "conformite": {{"observations": [...]}},
  "qualite_globale": 0.0-1.0
}}

Texte pour contexte:
{text}"""

    raw = await llm.llm_call(
        prompt,
        system=(
            "Tu es un auditeur comptable et juridique senior, prudent et factuel. "
            "Tu ne specules jamais. Tu identifies uniquement ce que le document montre. "
            "Reponds uniquement en JSON."
        ),
    )
    parsed = llm.parse_json(raw)

    return {
        **state,
        "analysis": parsed,
        "current_step": "analyze",
        "steps_completed": state.get("steps_completed", []) + ["analyze"],
    }
