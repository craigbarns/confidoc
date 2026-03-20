"""ConfiDoc Backend — Knowledge base ingestion/search endpoints."""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Query, status
from pydantic import BaseModel
from sqlalchemy import delete, or_, select

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import http_404
from app.models.document import Document
from app.models.document_version import DocumentVersion, DocumentVersionType
from app.models.kb_accounting_record import KbAccountingRecord
from app.models.kb_text_chunk import KbTextChunk
from app.models.llm_request import LlmRequest
from app.models.llm_suggestion import LlmSuggestion
from app.services.anonymization_service import anonymize_text, classify_document_type, extract_text_from_file
from app.services.storage_service import read_bytes

router = APIRouter()


class KbSearchRequest(BaseModel):
    query: str
    doc_type: str | None = None
    categorie_pcg: str | None = None
    include_needs_review: bool = False
    limit: int = 20


def _chunk_text(text: str, chunk_size: int = 800, overlap: int = 140) -> list[str]:
    if not text.strip():
        return []
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + chunk_size)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == n:
            break
        start = max(0, end - overlap)
    return chunks


_AMOUNT_PAT = re.compile(
    r"\b\d{1,3}(?:[\s\u00a0]?\d{3})*(?:[.,]\d{2})?\b\s*(?:€|EUR)?", re.IGNORECASE
)
_CODE_LINE_PAT = re.compile(r"^\s*(\d{3,6})\b")


def _pcg_category(code: str) -> str:
    mapping = [
        ("401", "fournisseur"),
        ("411", "client"),
        ("455", "associe_compte_courant"),
        ("467", "creance_diverse"),
        ("512", "banque_caisse"),
        ("53", "banque_caisse"),
        ("62", "honoraires"),
        ("63", "impots"),
        ("64", "personnel_charge"),
        ("66", "charges_financieres"),
        ("16", "emprunt"),
        ("26", "participation"),
        ("21", "immobilisation"),
    ]
    for prefix, category in mapping:
        if code.startswith(prefix):
            return category
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
    return classes.get(code[0], "autre") if code else "inconnu"


def _extract_accounting_records(text: str) -> list[dict]:
    records: list[dict] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m_code = _CODE_LINE_PAT.search(line)
        if not m_code:
            continue
        code = m_code.group(1)
        amounts = list(_AMOUNT_PAT.finditer(line))
        amount_raw = amounts[-1].group(0) if amounts else None
        records.append(
            {
                "code_comptable": code,
                "categorie_pcg": _pcg_category(code),
                "montant_raw": amount_raw,
                "libelle": line,
            }
        )
    return records


def _quality_flags(dataset_text: str) -> list[str]:
    flags: list[str] = []
    critical_patterns = {
        "emails_found": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "iban_found": r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b",
        "siret_found": r"\b\d{3}[ .-]?\d{3}[ .-]?\d{3}[ .-]?\d{5}\b",
        "siren_found": r"\b\d{3}[ .-]?\d{3}[ .-]?\d{3}\b",
        "uppercase_person_leftovers": r"\b[A-ZÀ-ÖØ-Ý]{2,}(?:\s+[A-ZÀ-ÖØ-Ý]{2,}){1,4}\b",
    }
    for flag, pat in critical_patterns.items():
        if re.search(pat, dataset_text):
            flags.append(flag)
    return flags


@router.post(
    "/ingest/{document_id}",
    status_code=status.HTTP_200_OK,
    summary="Ingest un document anonymisé dans la base de connaissances",
)
async def ingest_document_to_kb(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    try:
        document_uuid = uuid.UUID(document_id)
    except ValueError as exc:
        raise http_404("Document introuvable") from exc

    result = await db.execute(
        select(Document).where(
            Document.id == document_uuid,
            Document.uploaded_by_user_id == current_user.id,
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise http_404("Document introuvable")

    # get original text (from version if available)
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
        try:
            original_bytes = read_bytes(document.storage_backend, document.storage_key)
        except FileNotFoundError:
            if document.raw_content:
                original_bytes = document.raw_content
            else:
                raise http_404("Fichier source introuvable, ré-uploade le document.")
        original_text = extract_text_from_file(original_bytes, document.extension) or ""

    effective_type = classify_document_type(original_text, document.original_filename)
    dataset_text, detections = anonymize_text(
        original_text, profile="dataset_accounting", document_type=effective_type
    )

    # merge accepted LLM suggestions
    llm_suggestions_result = await db.execute(
        select(LlmSuggestion)
        .join(LlmRequest, LlmRequest.id == LlmSuggestion.llm_request_id)
        .where(
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
        }
        overlap = any(
            not (cand["end_index"] <= ex["start_index"] or cand["start_index"] >= ex["end_index"])
            for ex in merged
        )
        if not overlap:
            merged.append(cand)

    dataset_text = original_text
    for match in sorted(merged, key=lambda m: m["start_index"], reverse=True):
        dataset_text = (
            dataset_text[: match["start_index"]]
            + match["replacement"]
            + dataset_text[match["end_index"] :]
        )

    flags = _quality_flags(dataset_text)
    needs_review = len(flags) > 0 or len(merged) == 0

    # idempotent re-ingest: clear previous entries for this doc
    await db.execute(delete(KbAccountingRecord).where(KbAccountingRecord.document_id == document.id))
    await db.execute(delete(KbTextChunk).where(KbTextChunk.document_id == document.id))

    accounting_records = _extract_accounting_records(dataset_text)
    for rec in accounting_records:
        db.add(
            KbAccountingRecord(
                document_id=document.id,
                org_id=document.org_id,
                uploaded_by_user_id=document.uploaded_by_user_id,
                doc_type=effective_type,
                code_comptable=rec["code_comptable"],
                categorie_pcg=rec["categorie_pcg"],
                montant_raw=rec["montant_raw"],
                libelle=rec["libelle"],
                needs_review=needs_review,
            )
        )

    for idx, chunk in enumerate(_chunk_text(dataset_text)):
        db.add(
            KbTextChunk(
                document_id=document.id,
                org_id=document.org_id,
                uploaded_by_user_id=document.uploaded_by_user_id,
                doc_type=effective_type,
                chunk_index=idx,
                chunk_text=chunk,
                needs_review=needs_review,
            )
        )

    await db.commit()
    return {
        "status": "ingested",
        "document_id": str(document.id),
        "doc_type": effective_type,
        "quality": {"needs_review": needs_review, "quality_flags": flags},
        "counts": {
            "entities": len(merged),
            "accounting_records": len(accounting_records),
            "text_chunks": len(_chunk_text(dataset_text)),
        },
    }


@router.post(
    "/search",
    status_code=status.HTTP_200_OK,
    summary="Recherche dans la base de connaissances (records + chunks)",
)
async def search_kb(
    payload: KbSearchRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    q = payload.query.strip()
    if not q:
        return {"query": payload.query, "results": []}

    limit = max(1, min(100, payload.limit))
    query_like = f"%{q}%"

    rec_stmt = select(KbAccountingRecord).where(
        KbAccountingRecord.uploaded_by_user_id == current_user.id,
        or_(
            KbAccountingRecord.libelle.ilike(query_like),
            KbAccountingRecord.code_comptable.ilike(query_like),
            KbAccountingRecord.categorie_pcg.ilike(query_like),
        ),
    )
    if payload.doc_type:
        rec_stmt = rec_stmt.where(KbAccountingRecord.doc_type == payload.doc_type)
    if payload.categorie_pcg:
        rec_stmt = rec_stmt.where(KbAccountingRecord.categorie_pcg == payload.categorie_pcg)
    if not payload.include_needs_review:
        rec_stmt = rec_stmt.where(KbAccountingRecord.needs_review.is_(False))
    rec_stmt = rec_stmt.limit(limit)

    chunk_stmt = select(KbTextChunk).where(
        KbTextChunk.uploaded_by_user_id == current_user.id,
        KbTextChunk.chunk_text.ilike(query_like),
    )
    if payload.doc_type:
        chunk_stmt = chunk_stmt.where(KbTextChunk.doc_type == payload.doc_type)
    if not payload.include_needs_review:
        chunk_stmt = chunk_stmt.where(KbTextChunk.needs_review.is_(False))
    chunk_stmt = chunk_stmt.limit(limit)

    rec_res = await db.execute(rec_stmt)
    chunk_res = await db.execute(chunk_stmt)

    records = [
        {
            "type": "accounting_record",
            "document_id": str(r.document_id),
            "doc_type": r.doc_type,
            "code_comptable": r.code_comptable,
            "categorie_pcg": r.categorie_pcg,
            "montant_raw": r.montant_raw,
            "libelle": r.libelle,
            "needs_review": r.needs_review,
        }
        for r in rec_res.scalars().all()
    ]
    chunks = [
        {
            "type": "text_chunk",
            "document_id": str(c.document_id),
            "doc_type": c.doc_type,
            "chunk_index": c.chunk_index,
            "chunk_text": c.chunk_text,
            "needs_review": c.needs_review,
        }
        for c in chunk_res.scalars().all()
    ]

    return {
        "query": payload.query,
        "filters": {
            "doc_type": payload.doc_type,
            "categorie_pcg": payload.categorie_pcg,
            "include_needs_review": payload.include_needs_review,
        },
        "counts": {"records": len(records), "chunks": len(chunks)},
        "results": records + chunks,
    }

