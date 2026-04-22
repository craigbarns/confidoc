"""ConfiDoc Backend — Review Agent State Definition."""

from typing import Any, TypedDict
from app.services.review.constants import STEPS_ORDER


class ReviewState(TypedDict, total=False):
    anonymized_text: str
    entity_summary: dict[str, int]
    docling_tables: list[str]
    docling_sections: list[dict[str, Any]]
    doc_type: str
    doc_type_confidence: float
    extracted_data: dict[str, Any]
    analysis: dict[str, Any]
    findings: dict[str, list[dict[str, Any]]]
    review_note: str
    sections: dict[str, str]
    demandes_formelles: list[str]
    pieces_a_verifier: list[str]
    review_complement: dict[str, str]
    confidence: float
    verdict: str
    prochaines_actions: list[str]
    current_step: str
    steps_completed: list[str]
    error: str | None
    error_code: str | None
    degraded: bool


def initial_review_state(
    anonymized_text: str,
    entity_summary: dict[str, int] | None = None,
    **kwargs: Any,
) -> ReviewState:
    return {
        "anonymized_text": anonymized_text,
        "entity_summary": entity_summary or {},
        "docling_tables": kwargs.get("docling_tables", []),
        "docling_sections": kwargs.get("docling_sections", []),
        "doc_type": "",
        "doc_type_confidence": 0.0,
        "extracted_data": {},
        "analysis": {},
        "findings": {},
        "review_note": "",
        "sections": {},
        "confidence": 0.0,
        "verdict": "",
        "prochaines_actions": [],
        "demandes_formelles": [],
        "pieces_a_verifier": [],
        "review_complement": {},
        "current_step": "init",
        "steps_completed": [],
        "error": None,
        "error_code": None,
        "degraded": False,
    }


def fallback_findings(reason: str) -> dict[str, list[dict[str, Any]]]:
    return {
        "anomalies_confirmees": [],
        "points_attention": [
            {
                "description": "Analyse automatique complete indisponible",
                "detail": reason,
            }
        ],
        "informations_manquantes": [
            {
                "description": "Les donnees cles n'ont pas pu etre confirmees automatiquement",
                "detail": (
                    "Le document doit etre relu manuellement ou relance quand le fournisseur IA "
                    "redevient disponible."
                ),
            }
        ],
        "verifications_recommandees": [
            {
                "description": "Relancer l'analyse IA avant toute decision definitive",
                "detail": (
                    "La note ci-dessous est une synthese de secours, pas une revue cabinet "
                    "complete."
                ),
            }
        ],
    }


def fallback_review_state(
    state: ReviewState,
    *,
    reason: str,
    code: str = "llm_unavailable",
) -> ReviewState:
    text_len = len(state.get("anonymized_text") or "")
    entity_summary = state.get("entity_summary") or {}
    entity_count = sum(v for v in entity_summary.values() if isinstance(v, int))
    current_findings = state.get("findings") or {}
    findings = current_findings if any(current_findings.values()) else fallback_findings(reason)

    return {
        **state,
        "doc_type": state.get("doc_type") or "analyse_limitee",
        "doc_type_confidence": float(state.get("doc_type_confidence") or 0.0),
        "extracted_data": state.get("extracted_data") or {
            "objet": "Analyse IA limitee par indisponibilite temporaire",
            "references": [],
            "montants_cles": {},
            "entites_detectees": entity_summary,
        },
        "analysis": state.get("analysis") or {
            "completude": {
                "score": 0.0,
                "elements_manquants": ["Revue IA complete non executee"],
            },
            "coherence": {"score": 0.0, "observations": [reason]},
            "points_attention": ["Relance necessaire avant conclusion metier"],
            "conformite": {"observations": []},
            "qualite_globale": 0.0,
        },
        "findings": findings,
        "review_note": (
            "Analyse complete temporairement indisponible: le fournisseur IA limite ou refuse "
            "les requetes. Le document anonymise reste exploitable dans ConfiDoc, mais cette "
            "note doit etre consideree "
            "comme une synthese de secours. Relancez l'analyse avant toute conclusion definitive."
        ),
        "demandes_formelles": state.get("demandes_formelles") or [],
        "pieces_a_verifier": state.get("pieces_a_verifier") or [
            "Document anonymise source",
            "Pieces justificatives mentionnees dans le document",
            "Donnees cles a valider manuellement",
        ],
        "review_complement": state.get("review_complement") or {
            "identification": (
                f"Document anonymise disponible ({text_len} caracteres, "
                f"{entity_count} entites detectees)."
            ),
            "chiffres_cles": (
                "Extraction automatique limitee pendant l'indisponibilite du fournisseur IA."
            ),
        },
        "confidence": min(float(state.get("confidence") or 0.2), 0.35),
        "verdict": state.get("verdict") or "reserve",
        "prochaines_actions": state.get("prochaines_actions") or [
            "Relancer l'analyse IA dans quelques minutes.",
            "Effectuer une revue manuelle des montants, dates et parties avant decision.",
            "Verifier la configuration et le quota Mistral si l'erreur persiste.",
        ],
        "current_step": "synthesize",
        "steps_completed": list(STEPS_ORDER),
        "error": reason,
        "error_code": code,
        "degraded": True,
    }


def stream_payload(state: ReviewState) -> dict[str, Any]:
    return {k: v for k, v in state.items() if k not in {"anonymized_text"}}


def build_docling_context(state: ReviewState) -> str:
    """Construit le contexte à partir des tables/sections (optionnel, souvent vide)."""
    parts: list[str] = []
    tables = state.get("docling_tables") or []
    sections = state.get("docling_sections") or []

    if sections:
        headings = " > ".join(s.get("title", "") for s in sections[:15])
        parts.append(f"STRUCTURE DU DOCUMENT (sections): {headings}")

    if tables:
        parts.append(f"TABLEAUX DETECTES ({len(tables)}):")
        for i, tbl in enumerate(tables[:5], 1):
            truncated = tbl[:800] if len(tbl) > 800 else tbl
            parts.append(f"--- Tableau {i} ---\n{truncated}")

    return "\n".join(parts)
