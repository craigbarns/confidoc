"""ConfiDoc — One-click demo endpoint for investor pitches."""

import hashlib
import io
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.config import get_settings
from app.core.logging import get_logger
from app.models.document import Document, DocumentStatus
from app.models.membership import Membership
from app.services.storage_service import store_bytes
from app.workers.tasks import (
    anonymize_document_task,
    celery_workers_available,
    run_anonymize_document_inline,
)

router = APIRouter()
logger = get_logger(__name__)
settings = get_settings()

DEMO_DOC_PATH = Path(__file__).resolve().parent.parent.parent / "static" / "demo_doc.pdf"
_PUBLIC_DEMO_RATE_WINDOW = 60
_PUBLIC_DEMO_RATE_MAX = 10
_public_demo_attempts_fallback: dict[str, list[float]] = {}


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
    storage_backend, storage_key = store_bytes(content=content, extension="pdf")

    membership_res = await db.execute(
        select(Membership).where(
            Membership.user_id == current_user.id,
            Membership.is_active.is_(True),
        )
    )
    membership = membership_res.scalar_one_or_none()
    org_id = membership.org_id if membership else None

    document = Document(
        org_id=org_id,
        uploaded_by_user_id=current_user.id,
        original_filename="Bilan_Social_2025_Demo.pdf",
        content_type="application/pdf",
        extension="pdf",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        storage_backend=storage_backend,
        storage_key=storage_key,
        status=DocumentStatus.UPLOADED,
        raw_content=content if storage_backend == "database" else None,
        tags=["Démonstration"],
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    doc_id = str(document.id)
    if celery_workers_available(queue="nlp"):
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
    )

    return {
        "status": "processing",
        "document_id": doc_id,
        "original_filename": document.original_filename,
        "background_processing": background_processing,
        "message": "Document de démo créé. Anonymisation en cours en arrière-plan…",
    }
