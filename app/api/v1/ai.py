"""ConfiDoc Backend — AI endpoints (sur texte anonymisé uniquement)."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.api.v1._firewall import guard_inbound_response, guard_outbound_prompt
from app.api.v1._privacy_gate import privacy_gate_public_summary, require_privacy_gate
from app.config import get_settings
from app.core.exceptions import http_400, http_404
from app.core.logging import get_logger
from app.models.document import Document
from app.models.document_version import DocumentVersion, DocumentVersionType
from app.services.agents.privacy_gate import evaluate_document_privacy_gate
from app.services.llm_extraction_service import extract_with_llm
from app.services.mistral_service import generate_summary_with_mistral, stream_mistral_response
from app.services.ollama_service import generate_summary_with_ollama

router = APIRouter()
logger = get_logger(__name__)


def _apply_inbound_verdict(payload: dict, safe_text: str, fw_summary: dict | None) -> dict:
    """Enforce the inbound firewall verdict on a structured response.

    - block  → withhold the leaking payload (return a safe notice)
    - redact → return the PII-masked structure (tokens replace identifiers)
    - allow / firewall disabled → return the payload unchanged
    """
    verdict = (fw_summary or {}).get("verdict")
    if verdict == "block":
        return {
            "firewall_blocked": True,
            "message": (
                "Résultat retenu par l'AI Firewall : des données identifiantes ont été "
                "détectées dans la réponse. Renforcez l'anonymisation puis relancez."
            ),
        }
    if verdict == "redact":
        try:
            return json.loads(safe_text)
        except (ValueError, TypeError):
            return {
                "firewall_blocked": True,
                "message": "Réponse masquée par l'AI Firewall (données identifiantes).",
            }
    return payload


def _select_llm_provider(requested: str) -> str:
    """Sélectionne le meilleur provider disponible. Priorité: Mistral → Ollama."""
    s = get_settings()
    sensitive_mode = bool(getattr(s, "SENSITIVE_CLIENT_MODE", False))
    mistral_ok = bool(
        not sensitive_mode
        and getattr(s, "MISTRAL_ENABLED", False)
        and getattr(s, "MISTRAL_API_KEY", "")
    )
    ollama_ok = bool(getattr(s, "OLLAMA_ENABLED", True))

    if sensitive_mode:
        if requested == "ollama" and ollama_ok:
            return "ollama"
        return "disabled"
    if requested == "mistral" and mistral_ok:
        return "mistral"
    if requested == "ollama" and ollama_ok:
        return "ollama"
    if mistral_ok:
        return "mistral"
    if ollama_ok:
        return "ollama"
    return "disabled"


def _privacy_action_for_provider(provider: str) -> str:
    return "external_ai" if provider == "mistral" else "internal_review"


def _privacy_action_for_review_agent() -> str:
    s = get_settings()
    external_mistral_possible = bool(
        not getattr(s, "SENSITIVE_CLIENT_MODE", False)
        and getattr(s, "MISTRAL_ENABLED", False)
        and getattr(s, "MISTRAL_API_KEY", "")
    )
    return "external_ai" if external_mistral_possible else "internal_review"


async def _get_document_or_404(db: DbSession, document_id: str, user_id: uuid.UUID) -> Document:
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError as exc:
        raise http_404("Document introuvable") from exc

    result = await db.execute(
        select(Document).where(
            Document.id == doc_uuid,
            Document.uploaded_by_user_id == user_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise http_404("Document introuvable")
    return doc


async def _get_anonymized_text(db: DbSession, document: Document) -> str:
    """Récupère le texte anonymisé (final > preview)."""
    for version_type in (
        DocumentVersionType.FINAL_ANONYMIZED,
        DocumentVersionType.PREVIEW_ANONYMIZED,
    ):
        result = await db.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.version_type == version_type,
            )
        )
        version = result.scalar_one_or_none()
        if version and version.content_text:
            return version.content_text
    return ""


# ──────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/providers",
    response_class=JSONResponse,
    status_code=status.HTTP_200_OK,
    summary="Statut des providers LLM configurés",
)
async def ai_providers(current_user: CurrentUser) -> JSONResponse:
    s = get_settings()
    selected = _select_llm_provider("auto")
    sensitive_mode = bool(getattr(s, "SENSITIVE_CLIENT_MODE", False))
    return JSONResponse(
        {
            "selected_provider": selected,
            "sensitive_client_mode": sensitive_mode,
            "external_ai_enabled": bool(
                not sensitive_mode
                and getattr(s, "MISTRAL_ENABLED", False)
                and getattr(s, "MISTRAL_API_KEY", "")
            ),
            "policy_message": (
                "Mode client sensible actif : les appels IA externes sont désactivés."
                if sensitive_mode
                else "Analyse IA sur texte anonymisé uniquement."
            ),
            "mistral": {
                "enabled": bool(not sensitive_mode and getattr(s, "MISTRAL_ENABLED", False)),
                "key_set": bool(getattr(s, "MISTRAL_API_KEY", "")),
                "model": getattr(s, "MISTRAL_MODEL", ""),
            },
            "ollama": {"enabled": bool(getattr(s, "OLLAMA_ENABLED", True))},
        }
    )


@router.get(
    "/privacy-gate/{document_id}",
    response_class=JSONResponse,
    status_code=status.HTTP_200_OK,
    summary="Décision DPO agentique avant IA, export ou partage",
)
async def ai_privacy_gate(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
    requested_action: str = Query(
        default="external_ai",
        description="external_ai|export|share|demo|internal_review",
    ),
) -> JSONResponse:
    """Run the deterministic LangGraph Privacy Gate agent.

    The agent only consumes metadata, risk scores and anonymization state. It
    never returns raw or anonymized document text.
    """
    document = await _get_document_or_404(db, document_id, current_user.id)
    result = await evaluate_document_privacy_gate(
        db,
        document,
        requested_action=requested_action,
    )
    return JSONResponse(result)


@router.post(
    "/summary/{document_id}",
    response_class=JSONResponse,
    status_code=status.HTTP_200_OK,
    summary="Synthèse / Q&A sur le document anonymisé",
)
async def ai_summary(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
    question: str = Query(default=""),
    llm_provider: str = Query(default="auto"),
    mode: str = Query(default="summary"),
) -> JSONResponse:
    document = await _get_document_or_404(db, document_id, current_user.id)
    anonymized_text = await _get_anonymized_text(db, document)

    if not anonymized_text:
        raise http_400("Aucun texte anonymisé disponible. Lancez d'abord l'anonymisation.")

    if mode not in {"summary", "review", "draft", "question"}:
        raise http_400("Paramètre mode invalide. Valeurs: summary|review|draft|question.")
    if mode == "question" and not question.strip():
        raise http_400("Paramètre question requis quand mode=question.")

    # ── RAG enrichment for question mode ──
    rag_context = ""
    if mode == "question" and question.strip():
        try:
            from app.services.rag_service import build_rag_context

            rag_context = await build_rag_context(db, question, document.id, top_k=5)
        except Exception:
            pass

    text_for_llm = anonymized_text[:14000]
    if rag_context:
        # Prepend RAG context so the LLM can ground its answer
        text_for_llm = (
            f"[Contexte pertinent extrait du document]\n{rag_context}\n\n"
            f"[Document complet]\n{text_for_llm}"
        )[:16000]

    ai_payload = {
        "document_id": str(document.id),
        "anonymized_text": text_for_llm,
        "user_question": question.strip() or None,
    }

    selected_provider = _select_llm_provider(llm_provider)
    if selected_provider == "disabled":
        logger.info(
            "ai_summary_blocked_sensitive_mode",
            document_id=str(document.id),
            mode=mode,
        )
        return JSONResponse(
            {
                "document_id": str(document.id),
                "provider": "disabled",
                "model": None,
                "mode": mode,
                "summary": (
                    "Mode client sensible actif : l'analyse IA externe est désactivée. "
                    "Le document anonymisé reste disponible pour revue humaine et export sécurisé."
                ),
                "payload_policy": {
                    "raw_text_sent": False,
                    "anonymized_only": True,
                    "external_ai_disabled": True,
                },
            }
        )

    privacy_gate = await require_privacy_gate(
        db,
        document,
        _privacy_action_for_provider(selected_provider),
        anonymized_text=anonymized_text,
    )

    # ── AI Firewall (outbound): inspect the actual prompt for residual PII ──
    guarded_text, fw_prompt = await guard_outbound_prompt(ai_payload["anonymized_text"])
    ai_payload["anonymized_text"] = guarded_text

    try:
        if selected_provider == "mistral":
            llm = await generate_summary_with_mistral(ai_payload, prudent_mode=False, mode=mode)
            provider_name = "mistral"
        else:
            llm = await generate_summary_with_ollama(ai_payload)
            provider_name = "ollama"
    except Exception as exc:
        raise http_400(f"Erreur IA ({selected_provider}): {exc}") from exc

    parsed = llm.get("validated") or {}
    summary_text = json.dumps(parsed, ensure_ascii=False) if parsed else llm.get("raw_text", "")

    # ── AI Firewall (inbound): inspect the response before restitution ──
    summary_text, fw_response = await guard_inbound_response(summary_text)

    return JSONResponse(
        {
            "document_id": str(document.id),
            "provider": provider_name,
            "model": llm.get("model"),
            "mode": mode,
            "summary": summary_text,
            "payload_policy": {
                "raw_text_sent": False,
                "anonymized_only": True,
                "privacy_gate": privacy_gate_public_summary(privacy_gate),
                "firewall": {"prompt": fw_prompt, "response": fw_response},
            },
        }
    )


@router.post(
    "/stream/{document_id}",
    response_class=StreamingResponse,
    summary="Réponse IA en streaming (SSE) sur le document anonymisé",
)
async def ai_stream(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
    question: str = Query(default=""),
    llm_provider: str = Query(default="auto"),
):
    document = await _get_document_or_404(db, document_id, current_user.id)
    anonymized_text = await _get_anonymized_text(db, document)

    if not anonymized_text:

        async def _blocked():
            err = json.dumps({"error": "Aucun texte anonymisé. Lancez d'abord l'anonymisation."})
            yield f"data: {err}\n\n"

        return StreamingResponse(_blocked(), media_type="text/event-stream")

    prompt_question = question.strip() or "Fais une synthèse courte et claire de ce document."
    user_content = (
        f"Voici le texte anonymisé d'un document confidentiel:\n\n"
        f"{anonymized_text[:12000]}\n\n"
        f"Question: {prompt_question}"
    )

    stream_provider = _select_llm_provider(llm_provider)
    if stream_provider == "mistral":
        await require_privacy_gate(
            db,
            document,
            "external_ai",
            anonymized_text=anonymized_text,
        )
        # ── AI Firewall (outbound): inspect the prompt before streaming ──
        # Raises HTTP 400 on a block verdict; redacts residual PII otherwise.
        user_content, _ = await guard_outbound_prompt(user_content)

    async def _event_stream():
        try:
            if stream_provider == "disabled":
                logger.info(
                    "ai_stream_blocked_sensitive_mode",
                    document_id=str(document.id),
                )
                payload = json.dumps(
                    {"error": ("Mode client sensible actif : streaming IA externe désactivé.")},
                    ensure_ascii=False,
                )
                yield f"data: {payload}\n\n"
                yield "data: [DONE]\n\n"
                return
            if stream_provider == "mistral":
                gen = stream_mistral_response(user_content, temperature=0.3)
            else:
                # Streaming désactivé hors Mistral pour éviter les routages implicites.
                payload = json.dumps(
                    {
                        "error": (
                            "Streaming indisponible pour ce provider. "
                            "Configurez Mistral (MISTRAL_ENABLED + API key)."
                        )
                    },
                    ensure_ascii=False,
                )
                yield f"data: {payload}\n\n"
                yield "data: [DONE]\n\n"
                return
            # Buffer the model output server-side and inspect it BEFORE anything
            # reaches the client — nothing is restituted until the firewall clears it.
            collected: list[str] = []
            async for chunk in gen:
                collected.append(chunk)
            safe_text, fw_response = await guard_inbound_response("".join(collected))
            yield "data: " + json.dumps({"chunk": safe_text}, ensure_ascii=False) + "\n\n"
            if fw_response:
                yield "data: " + json.dumps({"firewall": fw_response}, ensure_ascii=False) + "\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            err = json.dumps({"error": str(exc)}, ensure_ascii=False)
            yield f"data: {err}\n\n"

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/extract/{document_id}",
    response_class=JSONResponse,
    status_code=status.HTTP_200_OK,
    summary="Extraction structurée 100% LLM (Mistral Large)",
)
async def ai_extract(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> JSONResponse:
    """Extrait les données structurées (type, montants, totaux) via Mistral Large.

    Pas de regex, pas de règles métier — uniquement un LLM sur le texte anonymisé.
    """
    document = await _get_document_or_404(db, document_id, current_user.id)
    anonymized_text = await _get_anonymized_text(db, document)

    if not anonymized_text:
        raise http_400("Aucun texte anonymisé disponible. Lancez d'abord l'anonymisation.")

    selected_provider = _select_llm_provider("auto")
    if selected_provider == "disabled":
        logger.info("ai_extract_blocked_sensitive_mode", document_id=str(document.id))
        extraction = {
            "type_document": "autre",
            "societe": {"denomination": None, "siret": None, "forme_juridique": None},
            "exercice": {"date_debut": None, "date_fin": None, "date_arrete": None},
            "montants_cles": [],
            "totaux": {
                "total_actif": {"montant": None, "source_snippet": None},
                "total_passif": {"montant": None, "source_snippet": None},
                "resultat_net": {"montant": None, "source_snippet": None},
                "chiffre_affaires": {"montant": None, "source_snippet": None},
            },
            "confiance": "low",
            "source": "disabled:sensitive_client_mode",
            "business_rules": {},
        }
    fw_prompt = None
    fw_response = None
    if selected_provider != "disabled":
        privacy_gate = await require_privacy_gate(
            db,
            document,
            _privacy_action_for_provider(selected_provider),
            anonymized_text=anonymized_text,
        )
        # ── AI Firewall (outbound): inspect the prompt before extraction ──
        guarded_text, fw_prompt = await guard_outbound_prompt(anonymized_text)
        extraction = await extract_with_llm(guarded_text)
        # ── AI Firewall (inbound): never return leaking structured data ──
        safe_text, fw_response = await guard_inbound_response(
            json.dumps(extraction, ensure_ascii=False)
        )
        extraction = _apply_inbound_verdict(extraction, safe_text, fw_response)

    payload_policy = {
        "method": extraction.get("source", "llm:mistral-large"),
        "anonymized_only": True,
        "external_ai_disabled": selected_provider == "disabled",
    }
    if selected_provider != "disabled":
        payload_policy["privacy_gate"] = privacy_gate_public_summary(privacy_gate)
        payload_policy["firewall"] = {"prompt": fw_prompt, "response": fw_response}

    return JSONResponse(
        {
            "document_id": str(document.id),
            "extraction": extraction,
            "payload_policy": payload_policy,
        }
    )


# ──────────────────────────────────────────────────────────────────────
# REVIEW AGENT (LangGraph)
# ──────────────────────────────────────────────────────────────────────


async def _get_review_structured_layout(_document: Document) -> dict:
    """Contexte structuré (tables/sections) pour l'agent de revue — sans Docling."""
    return {"tables": [], "sections": [], "available": False}


@router.post(
    "/review/{document_id}",
    response_class=StreamingResponse,
    summary="Analyse documentaire autonome (agent LangGraph multi-etapes)",
)
async def ai_review(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
):
    """Launch the LangGraph document review agent.

    Streams SSE events as each step completes:
    - classify: document type identification
    - extract: structured data extraction
    - analyze: business rules analysis
    - anomalies: inconsistency detection
    - synthesize: professional review note
    """
    document = await _get_document_or_404(db, document_id, current_user.id)
    anonymized_text = await _get_anonymized_text(db, document)

    if not anonymized_text:

        async def _blocked():
            payload = {
                "step": "error",
                "status": "error",
                "data": {
                    "error": "Aucun texte anonymise. Lancez d'abord l'anonymisation.",
                },
            }
            yield f"data: {json.dumps(payload)}\n\n"

        return StreamingResponse(_blocked(), media_type="text/event-stream")

    privacy_gate = await require_privacy_gate(
        db,
        document,
        _privacy_action_for_review_agent(),
        anonymized_text=anonymized_text,
    )

    # ── AI Firewall (outbound): inspect the prompt before the review agent ──
    # Raises HTTP 400 on block; redacts residual PII so nothing un-inspected
    # reaches the LLM-backed review pipeline.
    anonymized_text, _ = await guard_outbound_prompt(anonymized_text)

    # Get entity summary for richer analysis
    from app.models.entity_detection import EntityDetection

    entity_summary: dict[str, int] = {}
    try:
        det_result = await db.execute(
            select(EntityDetection).where(EntityDetection.document_id == document.id)
        )
        for det in det_result.scalars().all():
            etype = det.entity_type or "unknown"
            entity_summary[etype] = entity_summary.get(etype, 0) + 1
    except Exception:
        pass

    from app.services.review_agent import run_review_streaming

    layout_data = await _get_review_structured_layout(document)

    async def _event_stream():
        # Signal start
        yield (
            "data: "
            + json.dumps(
                {
                    "step": "classify",
                    "label": "Classification du document",
                    "status": "running",
                    "data": {"privacy_gate": privacy_gate_public_summary(privacy_gate)},
                },
                ensure_ascii=False,
            )
            + "\n\n"
        )

        try:
            async for event in run_review_streaming(
                anonymized_text,
                entity_summary,
                docling_tables=layout_data.get("tables", []),
                docling_sections=layout_data.get("sections", []),
            ):
                yield "data: " + json.dumps(event, ensure_ascii=False, default=str) + "\n\n"
        except Exception as exc:
            yield (
                "data: "
                + json.dumps(
                    {
                        "step": "error",
                        "label": "Erreur",
                        "status": "error",
                        "data": {"error": str(exc)[:300]},
                    }
                )
                + "\n\n"
            )

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/review-sync/{document_id}",
    response_class=JSONResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyse documentaire (mode synchrone, resultat complet)",
)
async def ai_review_sync(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> JSONResponse:
    """Run the full review agent and return complete results."""
    document = await _get_document_or_404(db, document_id, current_user.id)
    anonymized_text = await _get_anonymized_text(db, document)

    if not anonymized_text:
        raise http_400("Aucun texte anonymise. Lancez d'abord l'anonymisation.")

    privacy_gate = await require_privacy_gate(
        db,
        document,
        _privacy_action_for_review_agent(),
        anonymized_text=anonymized_text,
    )

    # ── AI Firewall (outbound): inspect the prompt before the review agent ──
    anonymized_text, fw_prompt = await guard_outbound_prompt(anonymized_text)

    from app.models.entity_detection import EntityDetection

    entity_summary: dict[str, int] = {}
    try:
        det_result = await db.execute(
            select(EntityDetection).where(EntityDetection.document_id == document.id)
        )
        for det in det_result.scalars().all():
            etype = det.entity_type or "unknown"
            entity_summary[etype] = entity_summary.get(etype, 0) + 1
    except Exception:
        pass

    from app.services.review_agent import run_review

    layout_data = await _get_review_structured_layout(document)

    result = await run_review(
        anonymized_text,
        entity_summary,
        docling_tables=layout_data.get("tables", []),
        docling_sections=layout_data.get("sections", []),
    )

    # Remove raw text from response
    result.pop("anonymized_text", None)

    # ── AI Firewall (inbound): never return a leaking review note ──
    safe_text, fw_response = await guard_inbound_response(
        json.dumps(result, ensure_ascii=False, default=str)
    )
    result = _apply_inbound_verdict(result, safe_text, fw_response)

    return JSONResponse(
        {
            "document_id": str(document.id),
            "privacy_gate": privacy_gate_public_summary(privacy_gate),
            "review": result,
            "firewall": {"prompt": fw_prompt, "response": fw_response},
        }
    )


# ──────────────────────────────────────────────────────────────────────
# RAG SEMANTIC SEARCH
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/rag-search/{document_id}",
    response_class=JSONResponse,
    status_code=status.HTTP_200_OK,
    summary="Recherche sémantique dans le document (RAG)",
)
async def rag_search(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
    q: str = Query(..., min_length=2, description="Question ou mots-clés"),
    top_k: int = Query(default=5, ge=1, le=20),
) -> JSONResponse:
    """Semantic search across document chunks using PGvector.

    Returns the most relevant text snippets with similarity scores.
    """
    document = await _get_document_or_404(db, document_id, current_user.id)

    from app.services.rag_service import search_similar

    chunks = await search_similar(db, q, top_k=top_k, document_filter=document.id)

    return JSONResponse(
        {
            "document_id": str(document.id),
            "query": q,
            "results": [
                {
                    "chunk_index": c.chunk_index,
                    "text": c.chunk_text,
                    "source_section": c.source_section,
                }
                for c in chunks
            ],
            "total": len(chunks),
        }
    )
