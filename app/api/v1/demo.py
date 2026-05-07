"""ConfiDoc — One-click demo endpoint for investor pitches."""

import hashlib
import io
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession, oauth2_scheme
from app.api.v1._doc_crud import _raw_document_content_type, _raw_document_disposition
from app.api.v1._doc_shared import _get_anonymized_text
from app.config import get_settings
from app.core.exceptions import http_404
from app.core.logging import get_logger
from app.core.security import decode_access_token, get_password_hash
from app.core.text_sanitize import postgres_safe_text
from app.models.document import Document, DocumentStatus
from app.models.document_version import DocumentVersion, DocumentVersionType
from app.models.entity_detection import EntityDetection
from app.models.membership import Membership
from app.models.pseudonym_mapping import PseudonymMapping
from app.models.user import User
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
PUBLIC_DEMO_USER_EMAIL = "demo-investor@confidoc.local"
_PUBLIC_DEMO_RATE_WINDOW = 60
_PUBLIC_DEMO_RATE_MAX = 10
_public_demo_attempts_fallback: dict[str, list[float]] = {}


def _demo_document_urls(document_id: str) -> dict[str, str]:
    base = f"/api/v1/demo/investor-document/{document_id}"
    return {
        "self": base,
        "raw": f"{base}/raw",
        "preview": f"{base}/preview",
        "score": f"{base}/score",
        "audit": f"{base}/audit",
        "export": f"{base}/export",
    }


def _authenticated_document_urls(document_id: str) -> dict[str, str]:
    base = f"/api/v1/documents/{document_id}"
    return {
        "self": base,
        "raw": f"{base}/raw",
        "preview": f"{base}/preview",
        "score": f"{base}/risk-score",
        "audit": f"{base}/audit-report",
        "export": f"{base}/export",
    }


async def _resolve_user_from_bearer_token(db: DbSession, token: str | None) -> User | None:
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        return None
    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        return None
    return user


async def _get_or_create_public_demo_user(db: DbSession) -> User:
    result = await db.execute(select(User).where(User.email == PUBLIC_DEMO_USER_EMAIL))
    user = result.scalar_one_or_none()
    if user:
        return user

    user = User(
        email=PUBLIC_DEMO_USER_EMAIL,
        password_hash=get_password_hash(f"Demo{uuid.uuid4().hex}1"),
        first_name="Demo",
        last_name="Investor",
        is_active=True,
        is_platform_admin=False,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        result = await db.execute(select(User).where(User.email == PUBLIC_DEMO_USER_EMAIL))
        user = result.scalar_one_or_none()
        if user:
            return user
        raise
    return user


def _is_public_demo_document(document: Document, user: User | None = None) -> bool:
    tags = set(str(item) for item in (document.tags or []))
    owner_email = getattr(user, "email", "")
    return (
        document.client_name == "Démo Investisseur"
        and "Investor Demo" in tags
        and owner_email == PUBLIC_DEMO_USER_EMAIL
    )


async def _get_public_demo_document_or_404(
    db: DbSession,
    document_id: str,
) -> tuple[Document, User]:
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError as exc:
        raise http_404("Document de démo introuvable") from exc

    result = await db.execute(
        select(Document, User)
        .join(User, User.id == Document.uploaded_by_user_id)
        .where(
            Document.id == doc_uuid,
            Document.is_deleted.is_(False),
            User.email == PUBLIC_DEMO_USER_EMAIL,
        )
    )
    row = result.first()
    if not row:
        raise http_404("Document de démo introuvable")
    document, user = row
    if not _is_public_demo_document(document, user):
        raise http_404("Document de démo introuvable")
    return document, user


async def _demo_document_payload(
    db: DbSession,
    document: Document,
    *,
    public_urls: bool = True,
) -> dict[str, Any]:
    original_text = ""
    preview_text = ""

    original_result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.ORIGINAL_TEXT,
        )
    )
    original_version = original_result.scalar_one_or_none()
    if original_version and getattr(original_version, "content_text", None):
        original_text = str(getattr(original_version, "content_text", ""))

    preview_result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.PREVIEW_ANONYMIZED,
        )
    )
    preview_version = preview_result.scalar_one_or_none()
    if preview_version and getattr(preview_version, "content_text", None):
        preview_text = str(getattr(preview_version, "content_text", ""))

    detections_result = await db.execute(
        select(EntityDetection).where(EntityDetection.document_id == document.id)
    )
    detections = list(detections_result.scalars().all())
    entity_summary: dict[str, int] = {}
    for detection in detections:
        entity_type = str(detection.entity_type or "unknown").upper()
        entity_summary[entity_type] = entity_summary.get(entity_type, 0) + 1

    risk_score = 0.0
    risk_level = "low"
    mapping_result = await db.execute(
        select(PseudonymMapping)
        .where(PseudonymMapping.document_id == document.id)
        .order_by(PseudonymMapping.created_at.desc())
    )
    mapping = mapping_result.scalar_one_or_none()
    if mapping and hasattr(mapping, "risk_score"):
        raw_score = float(getattr(mapping, "risk_score", None) or 0.0)
        risk_score = raw_score * 100 if 0 <= raw_score <= 1 else raw_score
        risk_level = getattr(mapping, "risk_level", None) or "low"

    status_value = (
        document.status.value if hasattr(document.status, "value") else str(document.status)
    )
    return {
        "status": status_value,
        "document_id": str(document.id),
        "document": {
            "id": str(document.id),
            "original_filename": document.original_filename,
            "content_type": document.content_type,
            "size_bytes": document.size_bytes,
            "status": status_value,
            "client_name": document.client_name,
            "synthetic": True,
        },
        "original_filename": document.original_filename,
        "size_bytes": document.size_bytes,
        "demo_mode": "investor",
        "client_name": document.client_name,
        "synthetic": True,
        "original_excerpt": original_text,
        "preview_text": preview_text,
        "anonymized_excerpt": preview_text,
        "detections_count": len(detections),
        "entity_summary": entity_summary,
        "risk": {
            "risk_score": round(risk_score, 1),
            "score": round(risk_score, 1),
            "level": risk_level,
            "risk_level": risk_level,
        },
        "urls": (
            _demo_document_urls(str(document.id))
            if public_urls
            else _authenticated_document_urls(str(document.id))
        ),
        "workflow": [
            "original",
            "anonymized",
            "decision",
            "score_explanation",
            "audit_trail",
            "export_report",
        ],
    }


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


async def _create_investor_demo_document(
    *,
    current_user: User,
    db: DbSession,
    background_tasks: BackgroundTasks,
    public_demo: bool = False,
) -> dict[str, Any]:
    if not DEMO_DOC_PATH.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document de démo non disponible",
        )

    content = DEMO_DOC_PATH.read_bytes()
    sha256 = hashlib.sha256(content).hexdigest()
    org_id = None if public_demo else await _resolve_demo_org_id(db, current_user)

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
        tags=["Démonstration", "Investor Demo", "Synthetic"],
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
        public_demo=public_demo,
    )
    try:
        await record_document_audit_event(
            db,
            document=document,
            action="document:demo_investor_loaded",
            details={
                "demo_mode": "investor",
                "synthetic": True,
                "public_demo": public_demo,
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

    payload = await _demo_document_payload(db, document, public_urls=public_demo)
    payload.update(
        {
            "status": "ready" if snapshot_ready else "processing",
            "background_processing": background_processing,
            "sensitive_client_mode": settings.SENSITIVE_CLIENT_MODE,
            "message": (
                "Démo investisseur chargée : document synthétique, original, "
                "anonymisation, scores, audit et export disponibles."
            ),
        }
    )
    return payload


@router.post(
    "/investor-document",
    status_code=status.HTTP_201_CREATED,
    summary="Créer ou charger un document synthétique de démo investisseur",
)
async def create_investor_demo_document(
    request: Request,
    db: DbSession,
    background_tasks: BackgroundTasks,
    token: str | None = Depends(oauth2_scheme),
) -> dict[str, Any]:
    """Create a synthetic investor demo document.

    Authenticated users get a normal personal demo document. Without auth, this
    endpoint is enabled only in demo mode and uses a dedicated synthetic demo
    owner so no real user data is exposed.
    """
    current_user = await _resolve_user_from_bearer_token(db, token)
    public_demo = current_user is None
    if public_demo:
        if not settings.DEMO_MODE or not settings.DEMO_SEED_ENABLED:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Démo investisseur désactivée sur cet environnement.",
            )
        client_ip = request.client.host if request.client else "unknown"
        await _check_public_demo_rate_limit(f"investor-document:{client_ip}")
        current_user = await _get_or_create_public_demo_user(db)

    payload = await _create_investor_demo_document(
        current_user=current_user,
        db=db,
        background_tasks=background_tasks,
        public_demo=public_demo,
    )
    payload["auth_mode"] = "demo_mode" if public_demo else "authenticated"
    return payload


@router.get(
    "/investor-document/{document_id}/raw",
    status_code=status.HTTP_200_OK,
    summary="Récupérer l'original synthétique de la démo investisseur",
)
async def get_investor_demo_raw(document_id: str, db: DbSession, request: Request) -> Response:
    document, _user = await _get_public_demo_document_or_404(db, document_id)
    try:
        from app.services.storage_service import read_document_bytes

        content = read_document_bytes(document)
        if not content:
            raise FileNotFoundError("empty demo raw content")
        return Response(
            content=content,
            media_type=_raw_document_content_type(document),
            headers={
                "Content-Disposition": _raw_document_disposition(document),
                "Content-Length": str(len(content)),
                "Accept-Ranges": "bytes",
                "X-ConfiDoc-Demo": "investor",
            },
        )
    except Exception as exc:
        logger.error(
            "get_investor_demo_raw_failed",
            doc_id=document_id,
            request_id=getattr(request.state, "request_id", None),
            error_type=type(exc).__name__,
        )
        raise http_404("Fichier original de démo introuvable.") from exc


@router.get(
    "/investor-document/{document_id}/preview",
    status_code=status.HTTP_200_OK,
    summary="Aperçu anonymisé du document synthétique investisseur",
)
async def get_investor_demo_preview(document_id: str, db: DbSession) -> dict[str, Any]:
    document, _user = await _get_public_demo_document_or_404(db, document_id)
    return await _demo_document_payload(db, document)


@router.get(
    "/investor-document/{document_id}/score",
    status_code=status.HTTP_200_OK,
    summary="Score RGPD du document synthétique investisseur",
)
async def get_investor_demo_score(document_id: str, db: DbSession) -> dict[str, Any]:
    _document, user = await _get_public_demo_document_or_404(db, document_id)
    from app.api.v1._doc_export import get_document_risk_score

    return await get_document_risk_score(document_id, user, db)


@router.get(
    "/investor-document/{document_id}/audit",
    status_code=status.HTTP_200_OK,
    summary="Audit trail du document synthétique investisseur",
)
async def get_investor_demo_audit(document_id: str, db: DbSession) -> dict[str, Any]:
    _document, user = await _get_public_demo_document_or_404(db, document_id)
    from app.api.v1._doc_export import get_audit_report

    return await get_audit_report(document_id, user, db)


@router.get(
    "/investor-document/{document_id}/export",
    response_class=PlainTextResponse,
    status_code=status.HTTP_200_OK,
    summary="Export texte anonymisé du document synthétique investisseur",
)
async def export_investor_demo_text(document_id: str, db: DbSession) -> PlainTextResponse:
    document, _user = await _get_public_demo_document_or_404(db, document_id)
    anonymized_text = await _get_anonymized_text(db, document)
    if not anonymized_text:
        raise http_404("Texte anonymisé de démo indisponible.")
    return PlainTextResponse(
        anonymized_text,
        headers={
            "Content-Disposition": 'attachment; filename="confidoc_demo_investor.txt"',
            "X-ConfiDoc-Demo": "investor",
        },
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
    return await _create_investor_demo_document(
        current_user=current_user,
        db=db,
        background_tasks=background_tasks,
        public_demo=False,
    )
