"""ConfiDoc Backend — Documents endpoints."""

import uuid
import re
from io import BytesIO

from typing import Literal

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from sqlalchemy import desc, delete as sql_delete, select, update

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import http_400, http_404
from app.models.document import Document, DocumentStatus
from app.models.document_version import DocumentVersion, DocumentVersionType
from app.models.entity_detection import EntityDetection
from app.models.llm_request import LlmRequest
from app.models.llm_suggestion import LlmSuggestion
from app.schemas.document import (
    AnonymizeResponse,
    DetectionResponse,
    DocumentPreviewResponse,
    DocumentResponse,
)
from app.services.document_processing_service import build_anonymization_preview
from app.services.anonymization_service import (
    anonymize_text,
    classify_document_type,
    extract_text_from_file,
)
from app.services.pdf_redaction_service import redact_pdf_bytes
from app.services.storage_service import delete_bytes, read_bytes

router = APIRouter()


async def _get_user_document_or_404(
    db: DbSession, document_id: str, user_id: uuid.UUID
) -> Document:
    try:
        document_uuid = uuid.UUID(document_id)
    except ValueError as exc:
        raise http_404("Document introuvable") from exc

    result = await db.execute(
        select(Document).where(
            Document.id == document_uuid,
            Document.uploaded_by_user_id == user_id,
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise http_404("Document introuvable")
    return document


@router.get(
    "",
    response_model=list[DocumentResponse],
    status_code=status.HTTP_200_OK,
    summary="Lister les documents de l'utilisateur",
)
async def list_documents(
    current_user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[Document]:
    result = await db.execute(
        select(Document)
        .where(Document.uploaded_by_user_id == current_user.id)
        .order_by(desc(Document.created_at))
        .limit(limit)
    )
    return list(result.scalars().all())


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Détail d'un document",
)
async def get_document(document_id: str, current_user: CurrentUser, db: DbSession) -> Document:
    return await _get_user_document_or_404(db, document_id, current_user.id)


@router.post(
    "/{document_id}/anonymize",
    response_model=AnonymizeResponse,
    status_code=status.HTTP_200_OK,
    summary="Anonymiser un document (preview)",
)
async def anonymize_document(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
    profile: Literal["moderate", "strict", "dataset_strict", "dataset_accounting"] = Query(default="moderate"),
    document_type: str = Query(default="auto"),
) -> AnonymizeResponse:
    document = await _get_user_document_or_404(db, document_id, current_user.id)
    file_content = read_bytes(document.storage_backend, document.storage_key)
    preview_text, detections, effective_type = await build_anonymization_preview(
        db=db,
        document=document,
        file_content=file_content,
        profile=profile,
        document_type=document_type,
    )
    await db.commit()

    return AnonymizeResponse(
        document_id=document.id,
        status=document.status.value,
        detections_count=len(detections),
        detections=[DetectionResponse(**item) for item in detections],
        preview_text=f"[type={effective_type}|profile={profile}]\\n\\n{preview_text}",
    )


@router.get(
    "/{document_id}/preview",
    response_model=DocumentPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Prévisualiser l'anonymisation",
)
async def preview_document(document_id: str, current_user: CurrentUser, db: DbSession) -> DocumentPreviewResponse:
    document = await _get_user_document_or_404(db, document_id, current_user.id)

    preview_result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.PREVIEW_ANONYMIZED,
        )
    )
    preview_version = preview_result.scalar_one_or_none()
    if not preview_version:
        raise http_404("Aucune preview disponible. Lance /anonymize d'abord")

    count_result = await db.execute(
        select(EntityDetection).where(EntityDetection.document_id == document.id)
    )
    detections_count = len(list(count_result.scalars().all()))

    return DocumentPreviewResponse(
        document_id=document.id,
        status=document.status.value,
        preview_text=preview_version.content_text,
        detections_count=detections_count,
    )


@router.post(
    "/{document_id}/validate",
    status_code=status.HTTP_200_OK,
    summary="Valider la preview et figer la version finale",
)
async def validate_document(document_id: str, current_user: CurrentUser, db: DbSession) -> dict:
    document = await _get_user_document_or_404(db, document_id, current_user.id)
    preview_result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.PREVIEW_ANONYMIZED,
        )
    )
    preview_version = preview_result.scalar_one_or_none()
    if not preview_version:
        raise http_404("Aucune preview disponible")

    await db.execute(
        delete(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.FINAL_ANONYMIZED,
        )
    )
    db.add(
        DocumentVersion(
            document_id=document.id,
            version_type=DocumentVersionType.FINAL_ANONYMIZED,
            content_text=preview_version.content_text,
        )
    )
    # Marquer l'approbation humaine des suggestions LLM pour cette preview.
    await db.execute(
        update(LlmRequest)
        .where(
            LlmRequest.document_id == document.id,
            LlmRequest.preview_version_id == preview_version.id,
        )
        .values(human_status="accepted")
    )
    await db.commit()
    return {"status": "validated", "document_id": str(document.id)}


@router.get(
    "/{document_id}/export",
    response_class=PlainTextResponse,
    status_code=status.HTTP_200_OK,
    summary="Exporter la version finale anonymisée (texte)",
)
async def export_document(document_id: str, current_user: CurrentUser, db: DbSession) -> PlainTextResponse:
    document = await _get_user_document_or_404(db, document_id, current_user.id)
    final_result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.FINAL_ANONYMIZED,
        )
    )
    final_version = final_result.scalar_one_or_none()
    if not final_version:
        raise http_404("Aucune version finale disponible. Lance /validate d'abord")

    return PlainTextResponse(final_version.content_text)


@router.get(
    "/{document_id}/export-pdf",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
    summary="Exporter un PDF visuellement redacted",
)
async def export_redacted_pdf(document_id: str, current_user: CurrentUser, db: DbSession) -> StreamingResponse:
    document = await _get_user_document_or_404(db, document_id, current_user.id)
    if document.extension.lower() != "pdf":
        raise http_400("Export PDF redacted disponible uniquement pour les PDF")

    detections_result = await db.execute(
        select(EntityDetection).where(EntityDetection.document_id == document.id)
    )
    detections = list(detections_result.scalars().all())
    if not detections:
        raise http_404("Aucune détection disponible. Lance /anonymize d'abord")

    original_bytes = read_bytes(document.storage_backend, document.storage_key)
    sensitive_values = [item.value_excerpt for item in detections]
    redacted_bytes = redact_pdf_bytes(original_bytes, sensitive_values)

    download_name = f"redacted_{document.original_filename}"
    headers = {"Content-Disposition": f'attachment; filename="{download_name}"'}
    return StreamingResponse(BytesIO(redacted_bytes), media_type="application/pdf", headers=headers)


@router.get(
    "/{document_id}/export-dataset",
    response_class=JSONResponse,
    status_code=status.HTTP_200_OK,
    summary="Exporter un enregistrement dataset (texte anonymisé + spans)",
)
async def export_dataset(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> JSONResponse:
    """Export RGPD-friendly pour dataset:
    - applique le profil 'dataset_accounting' (garde montants)
    - ne renvoie jamais les valeurs originales (pas de value_excerpt)
    - renvoie spans cohérents avec le texte anonymisé.
    """
    document = await _get_user_document_or_404(db, document_id, current_user.id)

    original_text: str | None = None
    original_result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.ORIGINAL_TEXT,
        )
    )
    original_version = original_result.scalar_one_or_none()
    if original_version:
        original_text = original_version.content_text

    if original_text is None:
        original_bytes = read_bytes(document.storage_backend, document.storage_key)
        original_text = extract_text_from_file(original_bytes, document.extension) or ""

    effective_type = classify_document_type(original_text, document.original_filename)
    dataset_text, detections = anonymize_text(
        original_text,
        profile="dataset_accounting",
        document_type=effective_type,
    )

    def overlaps(a: dict, b: dict) -> bool:
        return not (a["end_index"] <= b["start_index"] or a["start_index"] >= b["end_index"])

    def apply_replacements(text: str, dets: list[dict]) -> str:
        out = text
        for match in sorted(dets, key=lambda m: m["start_index"], reverse=True):
            out = (
                out[: match["start_index"]]
                + match["replacement"]
                + out[match["end_index"] :]
            )
        return out

    # Ajouter les suggestions LLM acceptées (humain = validate déjà appelé).
    llm_suggestions_result = await db.execute(
        select(LlmSuggestion).join(
            LlmRequest, LlmRequest.id == LlmSuggestion.llm_request_id
        ).where(
            LlmRequest.document_id == document.id,
            LlmRequest.human_status == "accepted",
        )
    )
    llm_suggestions = list(llm_suggestions_result.scalars().all())

    merged = list(detections)
    for s in llm_suggestions:
        cand = {
            "entity_type": s.entity_type,
            "start_index": int(s.start_index),
            "end_index": int(s.end_index),
            "replacement": s.replacement_token,
            # valeur non utilisée pour dataset export, mais utile pour uniformiser le schéma
            "value_excerpt": "",
        }
        if any(overlaps(cand, existing) for existing in merged):
            continue
        merged.append(cand)

    dataset_text = apply_replacements(original_text, merged)

    entities = [
        {
            "entity_type": item["entity_type"],
            "start": item["start_index"],
            "end": item["end_index"],
            "replacement_token": item["replacement"],
        }
        for item in merged
    ]

    # ----------------------------
    # Quality gate RGPD safe:
    # vérifier qu'on n'a pas laissé des patterns critiques dans le dataset final.
    # ----------------------------
    quality_flags: list[str] = []
    critical_patterns: dict[str, str] = {
        "emails_found": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "iban_found": r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b",
        "siret_found": r"\b\d{3}[ .-]?\d{3}[ .-]?\d{3}[ .-]?\d{5}\b",
        "siren_found": r"\b\d{3}[ .-]?\d{3}[ .-]?\d{3}\b",
        # Noms en clair (approx): suites de mots en MAJUSCULES
        "uppercase_person_leftovers": r"\b[A-ZÀ-ÖØ-Ý]{2,}(?:\s+[A-ZÀ-ÖØ-Ý]{2,}){1,4}\b",
    }
    for flag, pat in critical_patterns.items():
        if re.search(pat, dataset_text):
            quality_flags.append(flag)

    needs_review = len(quality_flags) > 0 or len(entities) == 0

    def pcg_category(code: str) -> str:
        if not code:
            return "inconnu"
        code = code.strip()
        if code.startswith("401"):
            return "fournisseur"
        if code.startswith("411"):
            return "client"
        if code.startswith("455"):
            return "associe_compte_courant"
        if code.startswith("467"):
            return "creance_diverse"
        if code.startswith("512") or code.startswith("53"):
            return "banque_caisse"
        if code.startswith("62"):
            return "honoraires"
        if code.startswith("63"):
            return "impots"
        if code.startswith("64"):
            return "personnel_charge"
        if code.startswith("66"):
            return "charges_financieres"
        if code.startswith("16"):
            return "emprunt"
        if code.startswith("26"):
            return "participation"
        if code.startswith("21"):
            return "immobilisation"
        classes = {
            "1": "capitaux",
            "2": "immobilisation",
            "3": "stock",
            "4": "tiers",
            "5": "tresorerie",
            "6": "charge",
            "7": "produit",
            "8": "autre",
        }
        return classes.get(code[0], "autre")

    amount_pat = re.compile(r"\b\d{1,3}(?:[ \u00a0]?\d{3})*(?:[.,]\d{2})?\b\s*(?:€|EUR)?", re.IGNORECASE)
    code_line_pat = re.compile(r"^\s*(\d{3,6})\b")

    def extract_accounting_records(text: str) -> list[dict]:
        records: list[dict] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            m_code = code_line_pat.search(line)
            if not m_code:
                continue
            code = m_code.group(1)
            amounts = list(amount_pat.finditer(line))
            amount_raw = amounts[-1].group(0) if amounts else None
            records.append(
                {
                    "code_comptable": code,
                    "categorie_pcg": pcg_category(code),
                    "montant_raw": amount_raw,
                    "libelle": line,
                }
            )
        return records

    accounting_records = extract_accounting_records(dataset_text)

    payload = {
        "document_id": str(document.id),
        "doc_type": effective_type,
        "profile": "dataset_accounting",
        "anonymized_text": dataset_text,
        "entities": entities,
        "quality": {
            "detections_count": len(entities),
            "needs_review": needs_review,
            "quality_flags": quality_flags,
        },
        "accounting_records": accounting_records,
    }
    return JSONResponse(payload)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer un document (et son fichier)",
    include_in_schema=True,
)
async def delete_document(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    document = await _get_user_document_or_404(db, document_id, current_user.id)

    # 1) Supprimer le fichier (best effort)
    delete_bytes(document.storage_backend, document.storage_key)

    # 2) Supprimer la base (cascade sur versions/detections)
    await db.execute(sql_delete(Document).where(Document.id == document.id))
    await db.commit()
