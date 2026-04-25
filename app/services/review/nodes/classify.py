"""ConfiDoc Backend — Review Agent Node: Classify."""

from app.services.review import llm
from app.services.review.state import ReviewState


async def classify_node(state: ReviewState) -> ReviewState:
    text = state["anonymized_text"][:8000]

    prompt = f"""Analyse ce texte anonymise et determine le type de document.

Types possibles: liasse_fiscale, bilan, compte_resultat, bail, statuts, facture,
contrat, courrier, correspondance, bulletin_paie, releve_bancaire, acte_notarie, declaration_tva,
proces_verbal, rapport_audit, note_frais, devis, autre.

Reponds en JSON strict:
{{"doc_type": "...", "confidence": 0.0-1.0, "sub_type": "...", "description": "..."}}

Texte:
{text}"""

    raw = await llm.llm_call(
        prompt,
        system="Tu es un classificateur de documents comptables et juridiques. Reponds uniquement en JSON.",
    )
    parsed = llm.parse_json(raw)

    return {
        **state,
        "doc_type": parsed.get("doc_type", "autre"),
        "doc_type_confidence": parsed.get("confidence", 0.5),
        "current_step": "classify",
        "steps_completed": state.get("steps_completed", []) + ["classify"],
    }
