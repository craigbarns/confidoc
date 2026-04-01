"""ConfiDoc — LangGraph Document Review Agent.

Multi-step autonomous agent that analyzes an anonymized document:
  1. Classify document type
  2. Extract structured key data
  3. Analyze against business rules
  4. Detect anomalies and inconsistencies
  5. Synthesize a professional review note

Uses Mistral Large via direct API (same as existing mistral_service).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

import httpx
from langgraph.graph import StateGraph, END

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# ── Agent State ─────────────────────────────────────────────────────────

class ReviewState(TypedDict, total=False):
    """State flowing through the review graph."""
    anonymized_text: str
    entity_summary: dict[str, int]
    doc_type: str
    doc_type_confidence: float
    extracted_data: dict[str, Any]
    analysis: dict[str, Any]
    anomalies: list[dict[str, Any]]
    review_note: str
    sections: dict[str, str]
    confidence: float
    current_step: str
    steps_completed: list[str]
    error: str | None


# ── LLM Call Helper ─────────────────────────────────────────────────────

async def _llm_call(prompt: str, *, system: str = "", temperature: float = 0.1) -> str:
    """Call Mistral Large and return raw text response."""
    settings = get_settings()
    if not settings.MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY manquant")

    headers = {
        "Authorization": f"Bearer {settings.MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    body = {
        "model": settings.MISTRAL_MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    timeout = float(settings.MISTRAL_TIMEOUT_SECONDS)

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{settings.MISTRAL_BASE_URL.rstrip('/')}/v1/chat/completions",
            headers=headers,
            json=body,
        )
    resp.raise_for_status()
    choices = (resp.json() or {}).get("choices") or []
    if not choices:
        return ""
    return str((choices[0] or {}).get("message", {}).get("content") or "")


def _parse_json(raw: str) -> dict[str, Any]:
    """Extract first JSON object from LLM response."""
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or start >= end:
        return {}
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {}


# ── Graph Nodes ─────────────────────────────────────────────────────────

async def classify_node(state: ReviewState) -> ReviewState:
    """Node 1: Classify document type."""
    text = state["anonymized_text"][:3000]

    prompt = f"""Analyse ce texte anonymise et determine le type de document.

Types possibles: liasse_fiscale, bilan, compte_resultat, bail, statuts, facture, 
contrat, bulletin_paie, releve_bancaire, acte_notarie, declaration_tva, 
proces_verbal, rapport_audit, note_frais, devis, autre.

Reponds en JSON strict:
{{"doc_type": "...", "confidence": 0.0-1.0, "sub_type": "...", "description": "..."}}

Texte:
{text}"""

    raw = await _llm_call(prompt, system="Tu es un classificateur de documents comptables et juridiques. Reponds uniquement en JSON.")
    parsed = _parse_json(raw)

    return {
        **state,
        "doc_type": parsed.get("doc_type", "autre"),
        "doc_type_confidence": parsed.get("confidence", 0.5),
        "current_step": "classify",
        "steps_completed": state.get("steps_completed", []) + ["classify"],
    }


async def extract_node(state: ReviewState) -> ReviewState:
    """Node 2: Extract structured data based on document type."""
    text = state["anonymized_text"][:6000]
    doc_type = state.get("doc_type", "autre")
    entity_summary = state.get("entity_summary", {})

    prompt = f"""Tu analyses un document de type: {doc_type}
Entites detectees: {json.dumps(entity_summary, ensure_ascii=False)}

Extrais les donnees structurees cles de ce document.

Reponds en JSON strict:
{{
  "parties": ["liste des parties/acteurs mentionnes"],
  "dates_cles": {{"description": "date"}},
  "montants_cles": {{"description": montant_numerique}},
  "references": ["numeros de reference, dossier, contrat..."],
  "objet": "objet principal du document",
  "duree": "duree si applicable",
  "conditions_particulieres": ["conditions notables"]
}}

Texte anonymise:
{text}"""

    raw = await _llm_call(prompt, system="Tu es un expert en extraction de donnees documentaires. Reponds uniquement en JSON.")
    parsed = _parse_json(raw)

    return {
        **state,
        "extracted_data": parsed,
        "current_step": "extract",
        "steps_completed": state.get("steps_completed", []) + ["extract"],
    }


async def analyze_node(state: ReviewState) -> ReviewState:
    """Node 3: Analyze against business rules for the document type."""
    doc_type = state.get("doc_type", "autre")
    extracted = state.get("extracted_data", {})
    text = state["anonymized_text"][:4000]

    prompt = f"""Tu analyses un document de type: {doc_type}
Donnees extraites: {json.dumps(extracted, ensure_ascii=False)[:2000]}

Effectue une analyse metier:
1. Verifie la coherence des montants entre eux
2. Verifie que les elements obligatoires sont presents
3. Evalue la qualite et completude du document
4. Identifie les points d'attention pour un reviseur

Reponds en JSON strict:
{{
  "completude": {{"score": 0.0-1.0, "elements_manquants": [...]}},
  "coherence": {{"score": 0.0-1.0, "observations": [...]}},
  "points_attention": ["liste des points a verifier"],
  "conformite": {{"observations": [...], "risques": [...]}},
  "qualite_globale": 0.0-1.0
}}

Texte pour contexte:
{text}"""

    raw = await _llm_call(prompt, system="Tu es un auditeur comptable et juridique expert. Reponds uniquement en JSON.")
    parsed = _parse_json(raw)

    return {
        **state,
        "analysis": parsed,
        "current_step": "analyze",
        "steps_completed": state.get("steps_completed", []) + ["analyze"],
    }


async def anomalies_node(state: ReviewState) -> ReviewState:
    """Node 4: Detect anomalies and inconsistencies."""
    doc_type = state.get("doc_type", "autre")
    extracted = state.get("extracted_data", {})
    analysis = state.get("analysis", {})
    text = state["anonymized_text"][:4000]

    prompt = f"""Document de type: {doc_type}
Donnees extraites: {json.dumps(extracted, ensure_ascii=False)[:1500]}
Analyse precedente: {json.dumps(analysis, ensure_ascii=False)[:1500]}

Detecte les anomalies, incoherences et risques:
- Montants aberrants ou inhabituels
- Incoherences entre sections
- Informations contradictoires
- Risques juridiques ou fiscaux potentiels
- Ecarts par rapport aux normes du type de document

Reponds en JSON strict:
{{
  "anomalies": [
    {{
      "severite": "critique|majeure|mineure|information",
      "categorie": "montant|coherence|completude|juridique|fiscal|autre",
      "description": "...",
      "recommandation": "..."
    }}
  ],
  "score_risque_global": 0.0-1.0,
  "resume_risques": "..."
}}

Texte pour contexte:
{text}"""

    raw = await _llm_call(prompt, system="Tu es un detecteur d'anomalies documentaires expert. Reponds uniquement en JSON.")
    parsed = _parse_json(raw)

    anomalies = parsed.get("anomalies", [])

    return {
        **state,
        "anomalies": anomalies,
        "current_step": "anomalies",
        "steps_completed": state.get("steps_completed", []) + ["anomalies"],
    }


async def synthesize_node(state: ReviewState) -> ReviewState:
    """Node 5: Generate final review note."""
    doc_type = state.get("doc_type", "autre")
    extracted = state.get("extracted_data", {})
    analysis = state.get("analysis", {})
    anomalies = state.get("anomalies", [])
    entity_summary = state.get("entity_summary", {})

    n_anomalies = len(anomalies)
    critiques = [a for a in anomalies if a.get("severite") == "critique"]
    majeures = [a for a in anomalies if a.get("severite") == "majeure"]

    prompt = f"""Genere une note de revue professionnelle pour ce document.

Type: {doc_type}
Donnees cles: {json.dumps(extracted, ensure_ascii=False)[:2000]}
Analyse: {json.dumps(analysis, ensure_ascii=False)[:1500]}
Anomalies detectees: {n_anomalies} (dont {len(critiques)} critiques, {len(majeures)} majeures)
Detail anomalies: {json.dumps(anomalies[:10], ensure_ascii=False)[:1500]}
Entites anonymisees: {json.dumps(entity_summary, ensure_ascii=False)}

Reponds en JSON strict:
{{
  "titre": "Note de revue - [type document]",
  "resume_executif": "2-3 phrases de synthese",
  "sections": {{
    "identification": "Type, parties, objet",
    "chiffres_cles": "Montants et dates importantes",
    "analyse": "Points de controle et observations",
    "alertes": "Anomalies et risques identifies",
    "recommandations": "Actions a mener"
  }},
  "verdict": "favorable|reserve|defavorable",
  "confiance": 0.0-1.0,
  "prochaines_actions": ["action 1", "action 2", ...]
}}"""

    raw = await _llm_call(
        prompt,
        system="Tu es un reviseur comptable senior. Tu rediges des notes de revue claires et actionnables. Reponds uniquement en JSON.",
        temperature=0.2,
    )
    parsed = _parse_json(raw)

    return {
        **state,
        "review_note": parsed.get("resume_executif", ""),
        "sections": parsed.get("sections", {}),
        "confidence": parsed.get("confiance", 0.5),
        "current_step": "synthesize",
        "steps_completed": state.get("steps_completed", []) + ["synthesize"],
        "error": None,
    }


# ── Build Graph ─────────────────────────────────────────────────────────

def build_review_graph() -> StateGraph:
    """Build the document review LangGraph."""
    graph = StateGraph(ReviewState)

    graph.add_node("classify", classify_node)
    graph.add_node("extract", extract_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("anomalies", anomalies_node)
    graph.add_node("synthesize", synthesize_node)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "extract")
    graph.add_edge("extract", "analyze")
    graph.add_edge("analyze", "anomalies")
    graph.add_edge("anomalies", "synthesize")
    graph.add_edge("synthesize", END)

    return graph


_compiled_graph = None


def get_review_graph():
    """Get or create the compiled review graph (singleton)."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_review_graph().compile()
    return _compiled_graph


async def run_review(
    anonymized_text: str,
    entity_summary: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Run the full review pipeline and return the final state."""
    graph = get_review_graph()

    initial_state: ReviewState = {
        "anonymized_text": anonymized_text,
        "entity_summary": entity_summary or {},
        "doc_type": "",
        "doc_type_confidence": 0.0,
        "extracted_data": {},
        "analysis": {},
        "anomalies": [],
        "review_note": "",
        "sections": {},
        "confidence": 0.0,
        "current_step": "init",
        "steps_completed": [],
        "error": None,
    }

    try:
        final_state = await graph.ainvoke(initial_state)
        return dict(final_state)
    except Exception as exc:
        logger.error("review_agent_failed", error=str(exc))
        return {
            **initial_state,
            "error": f"{type(exc).__name__}: {str(exc)[:300]}",
            "current_step": "error",
        }


async def run_review_streaming(
    anonymized_text: str,
    entity_summary: dict[str, int] | None = None,
):
    """Run review pipeline yielding step updates as they complete.
    
    Yields dicts: {"step": str, "status": "running"|"done"|"error", "data": ...}
    """
    graph = get_review_graph()

    initial_state: ReviewState = {
        "anonymized_text": anonymized_text,
        "entity_summary": entity_summary or {},
        "doc_type": "",
        "doc_type_confidence": 0.0,
        "extracted_data": {},
        "analysis": {},
        "anomalies": [],
        "review_note": "",
        "sections": {},
        "confidence": 0.0,
        "current_step": "init",
        "steps_completed": [],
        "error": None,
    }

    steps_order = ["classify", "extract", "analyze", "anomalies", "synthesize"]
    step_labels = {
        "classify": "Classification du document",
        "extract": "Extraction des donnees cles",
        "analyze": "Analyse metier",
        "anomalies": "Detection d'anomalies",
        "synthesize": "Redaction de la note de revue",
    }

    last_completed = set()

    try:
        async for state in graph.astream(initial_state):
            # LangGraph astream yields {node_name: state_update}
            for node_name, node_output in state.items():
                if node_name in steps_order:
                    yield {
                        "step": node_name,
                        "label": step_labels.get(node_name, node_name),
                        "status": "done",
                        "data": {
                            k: v for k, v in node_output.items()
                            if k not in ("anonymized_text",)
                        },
                    }
                    last_completed.add(node_name)

                    # Signal next step as running
                    idx = steps_order.index(node_name)
                    if idx + 1 < len(steps_order):
                        next_step = steps_order[idx + 1]
                        yield {
                            "step": next_step,
                            "label": step_labels.get(next_step, next_step),
                            "status": "running",
                            "data": {},
                        }

        yield {"step": "complete", "label": "Analyse terminee", "status": "complete", "data": {}}

    except Exception as exc:
        logger.error("review_agent_stream_failed", error=str(exc))
        yield {
            "step": "error",
            "label": "Erreur",
            "status": "error",
            "data": {"error": f"{type(exc).__name__}: {str(exc)[:300]}"},
        }
