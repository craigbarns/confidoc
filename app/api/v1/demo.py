"""ConfiDoc — One-click demo endpoint for investor pitches."""

import hashlib
import io
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.config import get_settings
from app.core.logging import get_logger
from app.core.text_sanitize import postgres_safe_text
from app.models.document import Document, DocumentStatus
from app.models.document_version import DocumentVersion, DocumentVersionType
from app.models.entity_detection import EntityDetection
from app.models.membership import Membership
from app.models.pseudonym_mapping import PseudonymMapping
from app.services.audit_trail_service import record_document_audit_event
from app.services.crypto_service import encrypt_mapping
from app.services.rbac_service import require_org_permission
from app.services.storage_service import store_bytes
from app.workers.tasks import (
    anonymize_document_task,
    run_anonymize_document_inline,
    should_dispatch_document_task_to_celery,
)

router = APIRouter()
logger = get_logger(__name__)
settings = get_settings()

DEMO_DOC_PATH = Path(__file__).resolve().parent.parent.parent / "static" / "demo_doc.pdf"
_PUBLIC_DEMO_RATE_WINDOW = 60
_PUBLIC_DEMO_RATE_MAX = 10
_public_demo_attempts_fallback: dict[str, list[float]] = {}


async def _resolve_demo_org_id(db: DbSession, current_user: CurrentUser) -> Any | None:
    """Scope demo docs to an org when allowed, otherwise keep a personal demo doc.

    The investor demo uses synthetic data. It must stay zero-friction for live
    demos, including viewer/demo accounts, while still avoiding unauthorized
    writes into an organization namespace.
    """
    org_id = getattr(current_user, "org_id", None)
    if org_id is None:
        membership_res = await db.execute(
            select(Membership)
            .where(
                Membership.user_id == current_user.id,
                Membership.is_active.is_(True),
            )
            .order_by(Membership.created_at.asc())
        )
        membership = membership_res.scalars().first()
        org_id = membership.org_id if membership else None

    if org_id is None:
        return None

    try:
        await require_org_permission(
            db,
            user_id=current_user.id,
            org_id=org_id,
            permission="documents.upload",
        )
    except HTTPException as exc:
        if exc.status_code == status.HTTP_403_FORBIDDEN:
            logger.info(
                "demo_org_scope_skipped",
                user_id=str(current_user.id),
                reason="upload_permission_denied",
            )
            return None
        raise
    return org_id


async def _materialize_demo_snapshot(db: DbSession, document: Document) -> bool:
    """Persist a deterministic ready demo result for live investor demos.

    The dashboard demo must not depend on a live OCR/LLM call. Public demo cache
    already contains a synthetic, pre-anonymized payload, so authenticated demo
    documents can reuse that snapshot and become immediately inspectable.
    """
    try:
        from app.services.demo_service import get_demo_result

        result = await get_demo_result()
    except Exception as exc:
        logger.warning("demo_snapshot_unavailable", error_type=type(exc).__name__)
        return False

    if not isinstance(result, dict) or result.get("status") != "ready":
        return False

    original_text = str(result.get("original_excerpt") or "").strip()
    anonymized_text = str(result.get("anonymized_excerpt") or "").strip()
    if not anonymized_text:
        return False

    original_version = DocumentVersion(
        document_id=document.id,
        version_type=DocumentVersionType.ORIGINAL_TEXT,
        content_text=postgres_safe_text(original_text or "Document de démonstration synthétique."),
    )
    preview_version = DocumentVersion(
        document_id=document.id,
        version_type=DocumentVersionType.PREVIEW_ANONYMIZED,
        content_text=postgres_safe_text(anonymized_text),
    )
    db.add(original_version)
    db.add(preview_version)
    await db.flush()

    raw_detections = result.get("detections")
    detections = raw_detections if isinstance(raw_detections, list) else []
    for item in detections[:120]:
        if not isinstance(item, dict):
            continue
        db.add(
            EntityDetection(
                document_id=document.id,
                document_version_id=preview_version.id,
                entity_type=str(item.get("entity_type") or "unknown")[:40],
                start_index=int(item.get("start_index") or 0),
                end_index=int(item.get("end_index") or 0),
                value_excerpt=postgres_safe_text(str(item.get("value_excerpt") or ""))[:1000],
                replacement=postgres_safe_text(str(item.get("replacement") or "[REDACTED]"))[:500],
            )
        )

    risk = result.get("risk") if isinstance(result.get("risk"), dict) else {}
    try:
        encrypted_mapping = encrypt_mapping({}, settings.PSEUDO_MAPPING_KEY)
        expires_at = datetime.now(UTC) + timedelta(days=settings.RETENTION_MAPPING_DAYS)
        db.add(
            PseudonymMapping(
                document_id=document.id,
                user_id=document.uploaded_by_user_id,
                encrypted_mapping=encrypted_mapping,
                expires_at=expires_at,
                human_validated=False,
                risk_score=float(risk.get("score") or 0.0),
                risk_level=str(risk.get("level") or "low"),
            )
        )
    except Exception as exc:
        logger.warning("demo_snapshot_mapping_failed", error_type=type(exc).__name__)

    document.status = DocumentStatus.READY
    for action, details in (
        (
            "pipeline:extract",
            {
                "method": result.get("extraction_method") or "demo_snapshot",
                "provider": result.get("extraction_provider") or "demo_snapshot",
                "pages": result.get("pages") or 0,
            },
        ),
        (
            "pipeline:anonymize",
            {
                "method": "demo_snapshot",
                "profile": "investor_demo",
                "document_type": result.get("document_type") or "auto",
                "detections_count": int(result.get("detections_count") or len(detections)),
                "entity_summary": result.get("entity_summary") or {},
            },
        ),
        (
            "pipeline:risk_score",
            {
                "risk_score": float(risk.get("score") or 0.0),
                "risk_level": str(risk.get("level") or "low"),
            },
        ),
        (
            "pipeline:ready",
            {
                "mode": "demo_snapshot",
                "trust_score": result.get("trust_score"),
                "ai_readiness_score": result.get("ai_readiness_score"),
            },
        ),
    ):
        await record_document_audit_event(
            db,
            document=document,
            action=action,
            details=details,
        )

    await db.commit()
    await db.refresh(document)
    return True


async def _check_public_demo_rate_limit(key: str) -> None:
    """Limit public demo calls without making Redis a hard dependency."""
    redis_key = f"confidoc:demo_public_rl:{key}"
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=1)
        async with r:
            pipe = r.pipeline()
            pipe.incr(redis_key)
            pipe.expire(redis_key, _PUBLIC_DEMO_RATE_WINDOW)
            results = await pipe.execute()
            count = int(results[0])
        if count > _PUBLIC_DEMO_RATE_MAX:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Trop de requêtes de démo. Réessayez dans une minute.",
            )
        return
    except HTTPException:
        raise
    except Exception as exc:
        logger.debug("public_demo_rate_limit_redis_unavailable", error=str(exc))

    now = time.time()
    attempts = _public_demo_attempts_fallback.get(key, [])
    attempts = [t for t in attempts if now - t < _PUBLIC_DEMO_RATE_WINDOW]
    if len(attempts) >= _PUBLIC_DEMO_RATE_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de requêtes de démo. Réessayez dans une minute.",
        )
    attempts.append(now)
    _public_demo_attempts_fallback[key] = attempts


@router.get(
    "/public",
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="Résultat de démo public sans authentification",
)
async def get_public_demo(request: Request) -> Any:
    """Return the pre-computed public demo result without authentication."""
    from app.services.demo_service import get_demo_result

    client_ip = request.client.host if request.client else "unknown"
    await _check_public_demo_rate_limit(client_ip)

    result = await get_demo_result()
    if result is None:
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "status": "warming_up",
                "message": "La démo se prépare. Réessayez dans quelques secondes.",
            },
        )
    return result


@router.get(
    "/public/audit-report-pdf",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
    summary="Preuve DPO PDF de la démo publique",
)
async def get_public_demo_audit_report_pdf(request: Request) -> Any:
    """Return a no-auth PDF proof generated from the public demo result."""
    from app.services.demo_service import build_demo_audit_pdf, get_demo_result

    client_ip = request.client.host if request.client else "unknown"
    await _check_public_demo_rate_limit(f"pdf:{client_ip}")

    result = await get_demo_result()
    if result is None:
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "status": "warming_up",
                "message": "La preuve DPO se prépare. Réessayez dans quelques secondes.",
            },
        )

    pdf_bytes = build_demo_audit_pdf(result)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="preuve_dpo_confidoc_demo.pdf"'},
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Créer un document de démo",
)
async def create_demo_document(
    current_user: CurrentUser,
    db: DbSession,
    background_tasks: BackgroundTasks,
) -> dict:
    """Upload a pre-baked demo PDF and trigger background anonymization.

    Perfect for zero-friction investor demos — one click, full pipeline.
    """
    if not DEMO_DOC_PATH.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document de démo non disponible",
        )

    content = DEMO_DOC_PATH.read_bytes()
    sha256 = hashlib.sha256(content).hexdigest()
    org_id = await _resolve_demo_org_id(db, current_user)

    try:
        storage_backend, storage_key = store_bytes(content=content, extension="pdf")
    except Exception as exc:
        logger.warning(
            "demo_storage_primary_failed_using_database",
            configured_backend=settings.STORAGE_BACKEND,
            error_type=type(exc).__name__,
        )
        storage_backend = "database"
        storage_key = f"db://{sha256}.{uuid.uuid4().hex}.pdf"

    document = Document(
        org_id=org_id,
        uploaded_by_user_id=current_user.id,
        original_filename="Bilan_Social_2025_Demo.pdf",
        content_type="application/pdf",
        extension="pdf",
        size_bytes=len(content),
        sha256=sha256,
        storage_backend=storage_backend,
        storage_key=storage_key,
        status=DocumentStatus.UPLOADED,
        raw_content=content if storage_backend == "database" else None,
        tags=["Démonstration", "Investor Demo"],
        client_name="Démo Investisseur",
        exercice="2025",
        doc_category="bilan",
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    doc_id = str(document.id)
    snapshot_ready = await _materialize_demo_snapshot(db, document)
    if snapshot_ready:
        background_processing = "demo_snapshot"
    elif should_dispatch_document_task_to_celery(queue="nlp"):
        anonymize_document_task.delay(
            doc_id=doc_id,
            profile="strict",
            document_type="auto",
        )
        background_processing = "celery"
    else:
        background_tasks.add_task(
            run_anonymize_document_inline,
            doc_id=doc_id,
            profile="strict",
            document_type="auto",
        )
        background_processing = "api"

    logger.info(
        "demo_document_created",
        doc_id=doc_id,
        user_id=str(current_user.id),
        background_processing=background_processing,
        sensitive_client_mode=settings.SENSITIVE_CLIENT_MODE,
    )
    try:
        await record_document_audit_event(
            db,
            document=document,
            action="document:demo_investor_loaded",
            details={
                "demo_mode": "investor",
                "synthetic": True,
                "background_processing": background_processing,
                "sensitive_client_mode": settings.SENSITIVE_CLIENT_MODE,
                "workflow": [
                    "upload",
                    "ocr",
                    "anonymization",
                    "risk_score",
                    "trust_score",
                    "ai_readiness",
                    "audit_trail",
                    "export",
                ],
            },
        )
        await db.commit()
    except Exception as exc:
        logger.warning("demo_document_audit_failed", doc_id=doc_id, error=str(exc))
        await db.rollback()

    return {
        "status": "ready" if snapshot_ready else "processing",
        "document_id": doc_id,
        "original_filename": document.original_filename,
        "size_bytes": document.size_bytes,
        "demo_mode": "investor",
        "client_name": document.client_name,
        "synthetic": True,
        "background_processing": background_processing,
        "workflow": [
            "upload",
            "ocr",
            "anonymization",
            "risk_score",
            "trust_score",
            "ai_readiness",
            "audit_trail",
            "export",
        ],
        "sensitive_client_mode": settings.SENSITIVE_CLIENT_MODE,
        "message": (
            "Demo Investor chargée : document synthétique, OCR/anonymisation, "
            "scores et rapport d'audit en préparation."
        ),
    }
