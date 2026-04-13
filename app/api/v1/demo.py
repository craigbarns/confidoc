"""ConfiDoc — One-click demo endpoint for investor pitches."""

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.config import get_settings
from app.core.logging import get_logger
from app.models.document import Document, DocumentStatus
from app.models.membership import Membership
from app.workers.tasks import anonymize_document_task

router = APIRouter()
logger = get_logger(__name__)
settings = get_settings()

DEMO_DOC_PATH = Path(__file__).resolve().parent.parent.parent / "static" / "demo_doc.pdf"


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Créer un document de démo",
)
async def create_demo_document(
    current_user: CurrentUser,
    db: DbSession,
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
        sha256="demo_sha256_not_used",
        storage_backend="database",
        storage_key=f"db://demo_{uuid4().hex}",
        status=DocumentStatus.UPLOADED,
        raw_content=content,
        tags=["Démonstration"],
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    # Launch background Celery task immediately
    anonymize_document_task.delay(
        doc_id=str(document.id),
        content=content,
        profile="strict",
        document_type="auto",
    )

    logger.info(
        "demo_document_created",
        doc_id=str(document.id),
        user_id=str(current_user.id),
    )

    return {
        "status": "processing",
        "document_id": str(document.id),
        "original_filename": document.original_filename,
        "message": "Document de démo créé. Anonymisation en cours en arrière-plan…",
    }
