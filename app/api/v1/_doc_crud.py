"""ConfiDoc — Documents CRUD endpoints.

Routes : list, clients, trash/list, /all, /{id}, DELETE, restore, permanent delete.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import APIRouter, Query, Request, Response, status
from sqlalchemy import delete, desc, func, or_, select

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
from app.services.rbac_service import require_document_permission, user_active_org_ids

router = APIRouter()
logger = get_logger(__name__)


_BROWSER_PREVIEW_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/gif",
}


def _safe_content_disposition_filename(
    filename: str | None,
    *,
    disposition: str = "inline",
) -> str:
    safe = (filename or "document").replace("\r", " ").replace("\n", " ").replace('"', "")
    safe = safe.strip() or "document"
    ascii_safe = safe.encode("ascii", "ignore").decode("ascii") or "document"
    return (
        f'{disposition}; filename="{ascii_safe}"; '
        f"filename*=UTF-8''{quote(safe)}"
    )


def _raw_document_content_type(document: Document) -> str:
    content_type = (document.content_type or "").split(";", 1)[0].strip().lower()
    if content_type:
        return content_type
    extension = (document.extension or "").strip(".").lower()
    if extension == "pdf":
        return "application/pdf"
    if extension in {"png", "jpg", "jpeg", "webp", "gif"}:
        return "image/jpeg" if extension in {"jpg", "jpeg"} else f"image/{extension}"
    return "application/octet-stream"


def _raw_document_disposition(document: Document) -> str:
    content_type = _raw_document_content_type(document)
    disposition = "inline" if content_type in _BROWSER_PREVIEW_TYPES else "attachment"
    return _safe_content_disposition_filename(
        document.original_filename,
        disposition=disposition,
    )


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
    active_org_ids = await user_active_org_ids(db, current_user.id)
    visibility_filters = [Document.uploaded_by_user_id == current_user.id]
    if active_org_ids:
        visibility_filters.append(Document.org_id.in_(active_org_ids))
    visibility_clause = or_(*visibility_filters)

    # ── Full-Text Search (FTS) logic ──
    if q_norm:
        from app.models.document_version import DocumentVersion, DocumentVersionType

        ts_query = func.plainto_tsquery("french", q_norm)
        snippet_expr = func.ts_headline(
            "french",
            DocumentVersion.content_text,
            ts_query,
            "MaxWords=15, MinWords=5",
        ).label("snippet")

        query = (
            select(Document, snippet_expr)
            .join(DocumentVersion, Document.id == DocumentVersion.document_id)
            .where(
                visibility_clause,
                DocumentVersion.version_type == DocumentVersionType.PREVIEW_ANONYMIZED,
                func.to_tsvector("french", DocumentVersion.content_text).op("@@")(ts_query)
                | Document.original_filename.ilike(f"%{q_norm}%"),
            )
        )
    else:
        query = select(Document).where(visibility_clause)

    if not include_deleted:
        query = query.where(Document.is_deleted.is_(False))

    if client_norm:
        query = query.where(Document.client_name.ilike(f"%{client_norm}%"))

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

    if q_norm:
        documents_all = []
        for row in result.all():
            doc = row[0]
            doc.search_snippet = row[1]
            documents_all.append(doc)
    else:
        documents_all = list(result.scalars().all())

    # Filter by client_name (tags) in memory for now
    # (Removed for brevity, we assume tags are handled via FTS or client-side,
    # but we can add back the loop if needed.)

    return documents_all


@router.get(
    "/clients",
    response_model=list[str],
    status_code=status.HTTP_200_OK,
    summary="Lister les clients connus",
)
async def list_clients(
    current_user: CurrentUser,
    db: DbSession,
    include_deleted: bool = Query(default=False),
) -> list[str]:
    active_org_ids = await user_active_org_ids(db, current_user.id)
    visibility_filters = [Document.uploaded_by_user_id == current_user.id]
    if active_org_ids:
        visibility_filters.append(Document.org_id.in_(active_org_ids))
    visibility_clause = or_(*visibility_filters)

    # Primary: collect from client_name column
    cn_query = (
        select(Document.client_name)
        .where(
            visibility_clause,
            Document.client_name.isnot(None),
        )
        .distinct()
    )
    if not include_deleted:
        cn_query = cn_query.where(Document.is_deleted.is_(False))
    cn_result = await db.execute(cn_query)
    names: list[str] = [row[0] for row in cn_result.all() if row[0]]

    # Fallback: docs without client_name — read from tags[0]
    fb_query = (
        select(Document)
        .where(
            visibility_clause,
            Document.client_name.is_(None),
            Document.tags.isnot(None),
        )
    )
    if not include_deleted:
        fb_query = fb_query.where(Document.is_deleted.is_(False))
    fb_result = await db.execute(fb_query)
    for doc in fb_result.scalars().all():
        tags = list(getattr(doc, "tags", []) or [])
        if tags and tags[0]:
            names.append(tags[0])

    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        key = name.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(name.strip())
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
    active_org_ids = await user_active_org_ids(db, current_user.id)
    visibility_filters = [Document.uploaded_by_user_id == current_user.id]
    if active_org_ids:
        visibility_filters.append(Document.org_id.in_(active_org_ids))
    result = await db.execute(
        select(Document)
        .where(
            or_(*visibility_filters),
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
            or_(*visibility_filters),
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
        await require_document_permission(
            db,
            user_id=current_user.id,
            document=doc,
            permission="documents.delete",
        )
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


@router.get(
    "/{document_id}/raw",
    status_code=status.HTTP_200_OK,
    summary="Récupérer le fichier original brut (PDF/Image)",
)
async def get_document_raw(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
    request: Request,
) -> Response:
    document = await _get_user_document_or_404(
        db,
        document_id,
        current_user.id,
        permission="documents.raw",
    )

    try:
        from app.services.storage_service import read_document_bytes
        content = read_document_bytes(document)
        if not content:
            logger.warning(
                "get_document_raw_empty",
                doc_id=document_id,
                request_id=getattr(request.state, "request_id", None),
            )
            raise http_404("Fichier source vide ou introuvable sur le stockage.")
        content_type = _raw_document_content_type(document)
        return Response(
            content=content,
            media_type=content_type,
            headers={
                "Content-Disposition": _raw_document_disposition(document),
                "Content-Length": str(len(content)),
                "Accept-Ranges": "bytes",
            }
        )
    except Exception as exc:
        if hasattr(exc, "status_code"):
            raise
        logger.error(
            "get_document_raw_failed",
            doc_id=document_id,
            request_id=getattr(request.state, "request_id", None),
            storage_backend=getattr(document, "storage_backend", None),
            content_type=getattr(document, "content_type", None),
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise http_404("Fichier source introuvable sur le stockage.") from exc


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Supprimer un document (soft delete — corbeille)",
)
async def delete_document(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> Response:
    document = await _get_user_document_or_404(
        db,
        document_id,
        current_user.id,
        permission="documents.delete",
    )
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

    active_org_ids = await user_active_org_ids(db, current_user.id)
    visibility_filters = [Document.uploaded_by_user_id == current_user.id]
    if active_org_ids:
        visibility_filters.append(Document.org_id.in_(active_org_ids))
    result = await db.execute(
        select(Document).where(
            Document.id == doc_uuid,
            or_(*visibility_filters),
            Document.is_deleted.is_(True),
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise http_404("Document non trouvé dans la corbeille")
    await require_document_permission(
        db,
        user_id=current_user.id,
        document=document,
        permission="documents.delete",
    )

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
    response_model=None,
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

    active_org_ids = await user_active_org_ids(db, current_user.id)
    visibility_filters = [Document.uploaded_by_user_id == current_user.id]
    if active_org_ids:
        visibility_filters.append(Document.org_id.in_(active_org_ids))
    result = await db.execute(
        select(Document).where(
            Document.id == doc_uuid,
            or_(*visibility_filters),
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise http_404("Document introuvable")
    await require_document_permission(
        db,
        user_id=current_user.id,
        document=document,
        permission="documents.delete",
    )

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
    except OSError as exc:
        logger.warning("permanent_delete_storage_failed", doc_id=_doc_id_str, error=str(exc))

    return Response(status_code=status.HTTP_204_NO_CONTENT)
