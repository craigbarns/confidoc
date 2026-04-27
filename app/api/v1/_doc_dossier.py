"""ConfiDoc — Dossier endpoints: GET /dossiers, PATCH /{id}/metadata."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.api.v1._doc_shared import _get_user_document_or_404
from app.models.client import Client
from app.models.dossier import Dossier
from app.models.document import Document, DocumentStatus
from app.schemas.document import (
    DocumentMetadataPatch,
    DocumentResponse,
    DossierClient,
    DossierDoc,
    DossierExercice,
)

router = APIRouter()

_READY_STATUSES = {DocumentStatus.READY, DocumentStatus.ANONYMIZED}
_PROCESSING_STATUSES = {
    DocumentStatus.PROCESSING,
    DocumentStatus.EXTRACTING,
    DocumentStatus.EXTRACTED,
    DocumentStatus.ANONYMIZING,
}


@router.get(
    "/dossiers",
    response_model=list[DossierClient],
    status_code=status.HTTP_200_OK,
    summary="Structure Dossier groupée Client > Exercice",
)
async def get_dossiers(
    current_user: CurrentUser,
    db: DbSession,
    client_name: str = Query(default="", description="Filtrer par client (sous-chaîne, insensible à la casse)"),
) -> list[DossierClient]:
    """Retourne la structure dossier. 
    Priorise les entités Client/Dossier formelles, sinon repli sur les champs Document.client_name.
    """
    query = (
        select(Document)
        .where(
            Document.org_id == current_user.org_id,
            Document.is_deleted.is_(False),
        )
        .order_by(Document.client_name, desc(Document.exercice), desc(Document.created_at))
    )
    if client_name.strip():
        query = query.where(Document.client_name.ilike(f"%{client_name.strip()}%"))

    result = await db.execute(query)
    docs = list(result.scalars().all())

    # Group in Python: client_name → exercice → list[doc]
    clients: dict[str, dict[str | None, list[Document]]] = {}
    for doc in docs:
        cname = doc.client_name or "Sans Client"
        if cname not in clients:
            clients[cname] = {}
        ex = doc.exercice or "Sans Exercice"
        if ex not in clients[cname]:
            clients[cname][ex] = []
        clients[cname][ex].append(doc)

    out: list[DossierClient] = []
    for cname, exercice_map in clients.items():
        exercices: list[DossierExercice] = []
        all_dates: list[datetime] = []
        total = 0
        for ex, ex_docs in exercice_map.items():
            ready = sum(1 for d in ex_docs if d.status in _READY_STATUSES)
            processing = sum(1 for d in ex_docs if d.status in _PROCESSING_STATUSES)
            cats = sorted({d.doc_category for d in ex_docs if d.doc_category})
            dossier_docs = [
                DossierDoc(
                    id=d.id,
                    original_filename=d.original_filename,
                    doc_category=d.doc_category,
                    status=d.status.value if hasattr(d.status, "value") else str(d.status),
                    size_bytes=d.size_bytes,
                    created_at=d.created_at,
                )
                for d in ex_docs
            ]
            exercices.append(DossierExercice(
                exercice=ex,
                doc_count=len(ex_docs),
                ready_count=ready,
                processing_count=processing,
                doc_categories=cats,
                documents=dossier_docs,
            ))
            total += len(ex_docs)
            all_dates.extend(d.created_at for d in ex_docs if d.created_at)

        out.append(DossierClient(
            client_name=cname,
            exercices=exercices,
            total_docs=total,
            last_activity=max(all_dates) if all_dates else None,
        ))

    return sorted(out, key=lambda c: c.client_name.lower())


@router.patch(
    "/{document_id}/metadata",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Modifier les métadonnées dossier d'un document",
)
async def patch_document_metadata(
    document_id: str,
    patch: DocumentMetadataPatch,
    current_user: CurrentUser,
    db: DbSession,
) -> Document:
    doc = await _get_user_document_or_404(db, document_id, current_user.id)
    
    if patch.client_id is not None:
        doc.client_id = patch.client_id
        client = await db.get(Client, patch.client_id)
        if client:
            doc.client_name = client.name
            doc.tags = [client.name]

    if patch.dossier_id is not None:
        doc.dossier_id = patch.dossier_id
        dossier = await db.get(Dossier, patch.dossier_id)
        if dossier:
            doc.exercice = dossier.exercice
            doc.client_id = dossier.client_id

    if patch.client_name is not None:
        doc.client_name = patch.client_name
        doc.tags = [patch.client_name]
    
    if patch.exercice is not None:
        doc.exercice = patch.exercice
    
    if patch.doc_category is not None:
        doc.doc_category = patch.doc_category
        
    await db.commit()
    await db.refresh(doc)
    return doc
