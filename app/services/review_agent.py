"""ConfiDoc — LangGraph Document Review Agent v2.

Multi-step autonomous agent that analyzes an anonymized document:
  1. Classify document type
  2. Extract structured key data
  3. Analyze against business rules
  4. Identify findings (structured taxonomy, NOT flat anomalies)
  5. Filter: anti-alarmist downgrade pass
  6. Synthesize a professional review note

Taxonomy (4 tiers):
  A. anomalies_confirmees — only provable contradictions/errors in the document
  B. points_attention     — significant observations that deserve human review
  C. informations_manquantes — data gaps preventing complete analysis
  D. verifications_recommandees — hypotheses to validate with external sources
"""

from __future__ import annotations

import json
from typing import Any, TypedDict

import httpx
from langgraph.graph import StateGraph, END

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# ── Shared System Guardrails ────────────────────────────────────────────

_GUARDRAILS = """
REGLES ABSOLUES (non negociables):
- Ne JAMAIS qualifier un point de "non-conformite legale" sans contradiction chiffree explicite dans le document.
- Ne JAMAIS deduire l'existence d'une provision necessaire de la seule presence de dettes normales.
- Ne JAMAIS suggerer fraude, dissimulation, conflit d'interets ou prix de transfert sans indice documentaire direct et explicite.
- Ne JAMAIS affirmer qu'un ratio est "anormal" sans expliquer par rapport a quelle norme sectorielle precise.
- Ne JAMAIS utiliser "immediatement", "urgence", "sanctions" sauf si le document contient une echeance depassee prouvee.
- Preferer TOUJOURS "a verifier", "a documenter", "a confirmer" quand l'information est incomplete.
- Un poste comptable a zero n'est PAS une anomalie en soi.
- L'absence d'un element optionnel n'est PAS une anomalie.
- Des amortissements cumules eleves signifient simplement des actifs anciens, PAS un probleme.
- La mention de societes liees ne suffit PAS a evoquer les prix de transfert.
- Chaque finding doit etre UTILE et ACTIONNABLE pour un reviseur senior. Pas de remplissage.
- Maximum 6 findings au total. Qualite > quantite.
"""


def _build_docling_context(state: dict) -> str:
    """Build extra context from Docling structured extraction (tables, sections)."""
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


# ── Agent State ─────────────────────────────────────────────────────────

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


# ── LLM Call Helper ─────────────────────────────────────────────────────

async def _llm_call(prompt: str, *, system: str = "", temperature: float = 0.1) -> str:
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
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or start >= end:
        return {}
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {}


# ── Node 1: Classify ────────────────────────────────────────────────────

async def classify_node(state: ReviewState) -> ReviewState:
    text = state["anonymized_text"][:3000]

    prompt = f"""Analyse ce texte anonymise et determine le type de document.

Types possibles: liasse_fiscale, bilan, compte_resultat, bail, statuts, facture,
contrat, courrier, correspondance, bulletin_paie, releve_bancaire, acte_notarie, declaration_tva,
proces_verbal, rapport_audit, note_frais, devis, autre.

Reponds en JSON strict:
{{"doc_type": "...", "confidence": 0.0-1.0, "sub_type": "...", "description": "..."}}

Texte:
{text}"""

    raw = await _llm_call(
        prompt,
        system="Tu es un classificateur de documents comptables et juridiques. Reponds uniquement en JSON.",
    )
    parsed = _parse_json(raw)

    return {
        **state,
        "doc_type": parsed.get("doc_type", "autre"),
        "doc_type_confidence": parsed.get("confidence", 0.5),
        "current_step": "classify",
        "steps_completed": state.get("steps_completed", []) + ["classify"],
    }


# ── Node 2: Extract ─────────────────────────────────────────────────────

async def extract_node(state: ReviewState) -> ReviewState:
    text = state["anonymized_text"][:6000]
    doc_type = state.get("doc_type", "autre")
    entity_summary = state.get("entity_summary", {})
    docling_ctx = _build_docling_context(state)

    prompt = f"""Tu analyses un document de type: {doc_type}
Entites detectees: {json.dumps(entity_summary, ensure_ascii=False)}
{f"DONNEES STRUCTUREES (Docling):{chr(10)}{docling_ctx}" if docling_ctx else ""}

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

    raw = await _llm_call(
        prompt,
        system="Tu es un expert en extraction de donnees documentaires. Reponds uniquement en JSON.",
    )
    parsed = _parse_json(raw)

    return {
        **state,
        "extracted_data": parsed,
        "current_step": "extract",
        "steps_completed": state.get("steps_completed", []) + ["extract"],
    }


# ── Node 3: Analyze ─────────────────────────────────────────────────────

async def analyze_node(state: ReviewState) -> ReviewState:
    doc_type = state.get("doc_type", "autre")
    extracted = state.get("extracted_data", {})
    text = state["anonymized_text"][:4000]
    docling_ctx = _build_docling_context(state)

    prompt = f"""Tu analyses un document de type: {doc_type}
Donnees extraites: {json.dumps(extracted, ensure_ascii=False)[:2000]}
{f"DONNEES STRUCTUREES (Docling):{chr(10)}{docling_ctx}" if docling_ctx else ""}

Effectue une analyse metier factuelle:
1. Verifie la coherence des montants entre eux
2. Verifie que les elements obligatoires sont presents
3. Evalue la qualite et completude du document
4. Identifie les points d'attention pour un reviseur

{_GUARDRAILS}

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

    raw = await _llm_call(
        prompt,
        system=(
            "Tu es un auditeur comptable et juridique senior, prudent et factuel. "
            "Tu ne specules jamais. Tu identifies uniquement ce que le document montre. "
            "Reponds uniquement en JSON."
        ),
    )
    parsed = _parse_json(raw)

    return {
        **state,
        "analysis": parsed,
        "current_step": "analyze",
        "steps_completed": state.get("steps_completed", []) + ["analyze"],
    }


# ── Node 4: Findings (structured taxonomy) ──────────────────────────────

async def findings_node(state: ReviewState) -> ReviewState:
    doc_type = state.get("doc_type", "autre")
    extracted = state.get("extracted_data", {})
    analysis = state.get("analysis", {})
    text = state["anonymized_text"][:4000]
    docling_ctx = _build_docling_context(state)

    prompt = f"""Document de type: {doc_type}
Donnees extraites: {json.dumps(extracted, ensure_ascii=False)[:1500]}
Analyse precedente: {json.dumps(analysis, ensure_ascii=False)[:1500]}
{f"TABLEAUX ET STRUCTURE (Docling):{chr(10)}{docling_ctx}" if docling_ctx else ""}

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
Hypotheses a valider avec des sources EXTERNES (statuts, pieces, client):
- "Verifier la situation de liberation du capital aupres des statuts"
- "Confirmer la nature du poste X aupres du client"
Formulation obligatoire: "Verifier...", "Confirmer...", "Rapprocher..."

{_GUARDRAILS}

REGLE DE VOLUME: maximum 2 items par categorie, maximum 6 au total.
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

    raw = await _llm_call(
        prompt,
        system=(
            "Tu es un reviseur comptable senior avec 15 ans d'experience. "
            "Tu es connu pour ta rigueur et ton calme. Tu ne dramatises jamais. "
            "Tu distingues clairement fait prouve, observation, limite documentaire et hypothese. "
            "Tu preferes ne rien dire plutot que de speculer. "
            "Reponds uniquement en JSON."
        ),
    )
    parsed = _parse_json(raw)

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


# ── Node 5: Anti-Alarmist Filter ────────────────────────────────────────

_ALARMIST_KEYWORDS = [
    "immediatement", "urgence", "sanctions", "fraude", "dissimulation",
    "prix de transfert", "conflit d'interets", "non-conformite",
    "irregularite", "violation", "illegale", "penalite",
]

_DOWNGRADE_TRIGGERS = [
    "devrait avoir", "generalement", "habituellement", "normalement",
    "on s'attendrait", "il est courant", "en principe",
]


async def filter_node(state: ReviewState) -> ReviewState:
    """Post-processing: downgrade overly aggressive findings."""
    findings = state.get("findings", {})
    filtered = {
        "anomalies_confirmees": [],
        "points_attention": [],
        "informations_manquantes": list(findings.get("informations_manquantes", [])),
        "verifications_recommandees": list(findings.get("verifications_recommandees", [])),
    }

    for item in findings.get("anomalies_confirmees", []):
        desc = (item.get("description") or "").lower()
        detail = (item.get("detail") or "").lower()
        combined = desc + " " + detail

        if any(kw in combined for kw in _ALARMIST_KEYWORDS):
            filtered["verifications_recommandees"].append(item)
            continue

        if any(kw in combined for kw in _DOWNGRADE_TRIGGERS):
            filtered["points_attention"].append(item)
            continue

        filtered["anomalies_confirmees"].append(item)

    for item in findings.get("points_attention", []):
        desc = (item.get("description") or "").lower()
        detail = (item.get("detail") or "").lower()
        combined = desc + " " + detail

        if any(kw in combined for kw in _ALARMIST_KEYWORDS):
            filtered["verifications_recommandees"].append(item)
            continue

        filtered["points_attention"].append(item)

    for cat in filtered:
        filtered[cat] = filtered[cat][:3]

    return {
        **state,
        "findings": filtered,
        "current_step": "filter",
        "steps_completed": state.get("steps_completed", []) + ["filter"],
    }


# ── Node 6: Synthesize ──────────────────────────────────────────────────

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

Donnees extraites: {json.dumps(extracted, ensure_ascii=False)[:2000]}
Analyse: {json.dumps(analysis, ensure_ascii=False)[:1500]}
Constats structures (4 niveaux):
- Anomalies confirmees: {n_confirmed}
- Points d'attention: {n_attention}
- Informations manquantes: {n_missing}
- Verifications recommandees: {n_verif}
Detail constats: {json.dumps(findings, ensure_ascii=False)[:2000]}
Entites anonymisees: {json.dumps(entity_summary, ensure_ascii=False)}

{_GUARDRAILS}

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

    raw = await _llm_call(
        prompt,
        system=(
            "Tu es un senior en cabinet comptable ou juridique. Tu structures la reponse pour "
            "un collaborateur presse. Tu ne dramatises pas. Tu ne remplis pas de listes inutiles. "
            "Reponds uniquement en JSON."
        ),
        temperature=0.2,
    )
    parsed = _parse_json(raw)
    comp = parsed.get("complement") or {}
    if not isinstance(comp, dict):
        comp = {}

    return {
        **state,
        "review_note": parsed.get("resume_executif", ""),
        "demandes_formelles": [str(x) for x in (parsed.get("demandes_formelles") or []) if str(x).strip()][:12],
        "pieces_a_verifier": [str(x) for x in (parsed.get("pieces_a_verifier") or []) if str(x).strip()][:12],
        "prochaines_actions": [str(x) for x in (parsed.get("prochaines_actions") or []) if str(x).strip()][:12],
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


# ── Build Graph ─────────────────────────────────────────────────────────

def build_review_graph() -> StateGraph:
    graph = StateGraph(ReviewState)

    graph.add_node("classify", classify_node)
    graph.add_node("extract", extract_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("findings", findings_node)
    graph.add_node("filter", filter_node)
    graph.add_node("synthesize", synthesize_node)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "extract")
    graph.add_edge("extract", "analyze")
    graph.add_edge("analyze", "findings")
    graph.add_edge("findings", "filter")
    graph.add_edge("filter", "synthesize")
    graph.add_edge("synthesize", END)

    return graph


_compiled_graph = None


def get_review_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_review_graph().compile()
    return _compiled_graph


def _reset_graph():
    global _compiled_graph
    _compiled_graph = None


async def run_review(
    anonymized_text: str,
    entity_summary: dict[str, int] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    graph = get_review_graph()

    initial_state: ReviewState = {
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
    **kwargs: Any,
):
    """Yield step updates as they complete (SSE-friendly)."""
    graph = get_review_graph()

    initial_state: ReviewState = {
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
    }

    steps_order = ["classify", "extract", "analyze", "findings", "filter", "synthesize"]
    step_labels = {
        "classify": "Classification du document",
        "extract": "Extraction des donnees cles",
        "analyze": "Analyse metier",
        "findings": "Identification des constats",
        "filter": "Controle qualite des constats",
        "synthesize": "Synthese cabinet (5 blocs)",
    }

    def _iter_chunks(raw: object) -> dict[str, Any]:
        """Normalize LangGraph stream chunks to {node_name: update_dict}.

        Default astream() uses stream_mode='values' (full state per step): keys are
        state fields (doc_type, findings, …), NOT node names — so SSE never matched
        classify/extract/… and only accidentally collided with the state key 'findings'.
        We use stream_mode='updates' so each chunk is {node_name: node_output}.
        """
        if isinstance(raw, tuple) and len(raw) >= 2:
            mode, payload = raw[0], raw[1]
            if mode == "updates" and isinstance(payload, dict):
                return payload
            if isinstance(payload, dict):
                return payload
            return {}
        if isinstance(raw, dict):
            return raw
        return {}

    try:
        async for raw_chunk in graph.astream(initial_state, stream_mode="updates"):
            state = _iter_chunks(raw_chunk)
            for node_name, node_output in state.items():
                if node_name not in steps_order:
                    continue
                if not isinstance(node_output, dict):
                    continue
                yield {
                    "step": node_name,
                    "label": step_labels.get(node_name, node_name),
                    "status": "done",
                    "data": {
                        k: v
                        for k, v in node_output.items()
                        if k not in ("anonymized_text",)
                    },
                }

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
