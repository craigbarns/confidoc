"""ConfiDoc — Documents CRUD endpoints.

Routes : list, clients, trash/list, /all, /{id}, DELETE, restore, permanent delete.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import delete, desc, func, select

from app.api.deps import CurrentUser, DbSession
from app.api.v1._doc_shared import (
    _get_user_document_or_404,
    _normalize_client_name,
)
from app.core.exceptions import http_404
from app.core.logging import get_logger
from app.models.document import Document, DocumentStatus
from app.models.document_version import DocumentVersion
from app.models.entity_detection import EntityDetection
from app.schemas.document import DocumentResponse

router = APIRouter()
logger = get_logger(__name__)


@router.get(
    "/",
    response_model=list[DocumentResponse],
    status_code=status.HTTP_200_OK,
    summary="Lister les documents de l'utilisateur",
)
async def list_documents(
    current_user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    include_deleted: bool = Query(default=False),
    client_name: str = Query(default="", description="Filtrer par nom client (tag)"),
    q: str = Query(default="", description="Recherche texte sur le nom du document"),
    status_filter: str = Query(default="", description="uploaded|processing|ready|failed|deleted"),
) -> list[Document]:
    logger.info(
        "list_documents",
        user_id=str(current_user.id),
        limit=limit,
        offset=offset,
    )
    client_norm = _normalize_client_name(client_name)
    q_norm = _normalize_client_name(q)
    status_norm = _normalize_client_name(status_filter)

    query = select(Document).where(Document.uploaded_by_user_id == current_user.id)
    if not include_deleted:
        query = query.where(Document.is_deleted.is_(False))
    
    # ── Full-Text Search (FTS) logic ──
    if q_norm:
        # Join with document versions to search inside content
        from app.models.document_version import DocumentVersion, DocumentVersionType
        query = query.join(DocumentVersion).where(
            DocumentVersion.version_type == DocumentVersionType.PREVIEW_ANONYMIZED,
            func.to_tsvector('french', DocumentVersion.content_text).op('@@')(func.plainto_tsquery('french', q_norm)) | 
            Document.original_filename.ilike(f"%{q_norm}%")
        )

    if status_norm and status_norm != "deleted":
        if status_norm == "ready":
            query = query.where(
                Document.status.in_([DocumentStatus.READY, DocumentStatus.ANONYMIZED])
            )
        elif status_norm == "processing":
            query = query.where(
                Document.status.in_(
                    [
                        DocumentStatus.PROCESSING,
                        DocumentStatus.EXTRACTING,
                        DocumentStatus.EXTRACTED,
                        DocumentStatus.ANONYMIZING,
                    ]
                )
            )
        else:
            # Note: this might need adjustment depending on how your Enum is stored
            query = query.where(
                func.cast(Document.status, __import__("sqlalchemy").String).ilike(status_norm)
            )
    elif status_norm == "deleted":
        query = query.where(Document.is_deleted.is_(True))

    # Apply database pagination early
    query = query.order_by(desc(Document.created_at)).offset(offset).limit(limit)

    result = await db.execute(query)
    documents_all = list(result.scalars().all())

    # Filter by client_name (tags) in memory for now 
    if client_norm:
    return documents_all


@router.get(
    "/clients",
    response_model=list[str],
    status_code=status.HTTP_200_OK,
    summary="Lister les clients connus (tags documents)",
)
async def list_clients(
    current_user: CurrentUser,
    db: DbSession,
    include_deleted: bool = Query(default=False),
) -> list[str]:
    import re

    query = select(Document).where(Document.uploaded_by_user_id == current_user.id)
    if not include_deleted:
        query = query.where(Document.is_deleted.is_(False))
    result = await db.execute(query.order_by(desc(Document.created_at)))
    docs = list(result.scalars().all())

    seen: set[str] = set()
    out: list[str] = []
    for d in docs:
        tags = list(getattr(d, "tags", []) or [])
        if not tags:
            continue
        label = re.sub(r"\s+", " ", str(tags[0]).strip())
        key = _normalize_client_name(label)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(label)
    return sorted(out, key=lambda x: x.lower())


# ── CORBEILLE — routes statiques AVANT /{document_id} ────────────────


@router.get(
    "/trash/list",
    status_code=status.HTTP_200_OK,
    summary="Liste des documents supprimés (corbeille)",
)
async def list_trash(
    current_user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    result = await db.execute(
        select(Document)
        .where(
            Document.uploaded_by_user_id == current_user.id,
            Document.is_deleted.is_(True),
        )
        .order_by(desc(Document.deleted_at))
        .offset(offset)
        .limit(limit)
    )
    docs = result.scalars().all()

    count_result = await db.execute(
        select(func.count())
        .select_from(Document)
        .where(
            Document.uploaded_by_user_id == current_user.id,
            Document.is_deleted.is_(True),
        )
    )
    total = count_result.scalar()

    return {
        "documents": [
            {
                "id": str(d.id),
                "original_filename": d.original_filename,
                "size_bytes": d.size_bytes,
                "content_type": d.content_type,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "deleted_at": d.deleted_at.isoformat() if d.deleted_at else None,
                "doc_type": d.doc_type,
                "status": d.status.value if hasattr(d.status, "value") else str(d.status),
            }
            for d in docs
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.delete(
    "/all",
    status_code=status.HTTP_200_OK,
    summary="Supprimer tous mes documents (soft delete)",
)
async def delete_all_my_documents(
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    result = await db.execute(
        select(Document).where(
            Document.uploaded_by_user_id == current_user.id,
            Document.is_deleted.is_(False),
        )
    )
    docs = list(result.scalars().all())
    now = datetime.now(UTC)
    for doc in docs:
        doc.is_deleted = True
        doc.deleted_at = now
    await db.commit()
    return {"deleted_count": len(docs)}


# ── Routes paramétrées /{document_id} ────────────────────────────────


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Récupérer un document",
)
async def get_document(document_id: str, current_user: CurrentUser, db: DbSession) -> Document:
    return await _get_user_document_or_404(db, document_id, current_user.id)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer un document (soft delete — corbeille)",
)
async def delete_document(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> Response:
    document = await _get_user_document_or_404(db, document_id, current_user.id)
    document.is_deleted = True
    document.deleted_at = datetime.now(UTC)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{document_id}/restore",
    status_code=status.HTTP_200_OK,
    summary="Restaurer un document de la corbeille",
)
async def restore_document(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError as exc:
        raise http_404("Document introuvable") from exc

    result = await db.execute(
        select(Document).where(
            Document.id == doc_uuid,
            Document.uploaded_by_user_id == current_user.id,
            Document.is_deleted.is_(True),
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise http_404("Document non trouvé dans la corbeille")

    document.is_deleted = False
    document.deleted_at = None
    await db.commit()
    return {
        "message": "Document restauré avec succès",
        "document_id": str(document.id),
        "original_filename": document.original_filename,
    }


@router.delete(
    "/{document_id}/permanent",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Suppression définitive d'un document (RGPD)",
)
async def permanent_delete_document(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> Response:
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError as exc:
        raise http_404("Document introuvable") from exc

    result = await db.execute(
        select(Document).where(
            Document.id == doc_uuid,
            Document.uploaded_by_user_id == current_user.id,
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise http_404("Document introuvable")

    _storage_backend = document.storage_backend
    _storage_key = document.storage_key
    _doc_id_str = str(document.id)

    await db.execute(delete(EntityDetection).where(EntityDetection.document_id == doc_uuid))
    await db.execute(delete(DocumentVersion).where(DocumentVersion.document_id == doc_uuid))
    try:
        from app.models.pseudonym_mapping import PseudonymMapping

        await db.execute(delete(PseudonymMapping).where(PseudonymMapping.document_id == doc_uuid))
    except __import__("sqlalchemy").exc.SQLAlchemyError:
        pass
    await db.execute(delete(Document).where(Document.id == doc_uuid))
    await db.commit()

    try:
        if _storage_backend and _storage_key:
            from app.services.storage_service import delete_bytes

            delete_bytes(_storage_backend, _storage_key)
    except (IOError, OSError) as exc:
        logger.warning("permanent_delete_storage_failed", doc_id=_doc_id_str, error=str(exc))

    return Response(status_code=status.HTTP_204_NO_CONTENT)
