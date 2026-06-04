"""ConfiDoc — Helpers partagés entre les sous-modules documents.

Ce module ne contient PAS de routes FastAPI, uniquement des fonctions
utilitaires réutilisées par _doc_crud, _doc_stats, _doc_processing et _doc_export.
"""

from __future__ import annotations

import hashlib
import re
import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import http_400, http_404
from app.core.logging import get_logger
from app.core.text_sanitize import postgres_safe_text
from app.models.document import Document
from app.models.document_version import DocumentVersion, DocumentVersionType
from app.schemas.document import DetectionResponse
from app.services.rbac_service import require_document_permission, user_active_org_ids

logger = get_logger(__name__)


# ── Normalization ─────────────────────────────────────────────────────


def _normalize_client_name(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return re.sub(r"\s+", " ", raw).lower()


def _sha256_text(text: str | None) -> str | None:
    if not text:
        return None
    return hashlib.sha256(text.encode()).hexdigest()


def _detection_item_to_response(item: dict) -> DetectionResponse:
    return DetectionResponse(
        entity_type=item.get("entity_type", "UNKNOWN"),
        start_index=item.get("start_index", 0),
        end_index=item.get("end_index", 0),
        replacement=item.get("replacement", ""),
        confidence=item.get("confidence", 0.0),
        value_excerpt=item.get("value_excerpt", ""),
    )


def _infer_semantic_type(placeholder: str) -> str:
    """Map a placeholder token to a semantic entity type string."""
    p = placeholder.upper().strip("[]")
    # Substring matching — handles both bare tokens ([PERSONNE]) and
    # numbered variants ([PERSONNE_1], [SOCIETE_3], …)
    if "PERSONNE" in p or "PERSON" in p or "ASSOCIE" in p:
        return "PERSON"
    if "SOCIETE" in p or "COMPANY" in p or "CABINET" in p:
        return "COMPANY"
    if "ADRESSE" in p or "ADDRESS" in p or "LIEU" in p or "VILLE" in p or "CITY" in p or "APT" in p:
        return "ADDRESS"
    if "BANQUE" in p or "BANK" in p or "IBAN" in p or "BIC" in p:
        return "BANK"
    if "SIREN" in p or "SIRET" in p or "TVA" in p or "VAT" in p:
        return "COMPANY_ID"
    if "EMPRUNT" in p or "LOAN" in p:
        return "LOAN_REF"
    if "NAISSANCE" in p or "BIRTH" in p:
        return "BIRTH_INFO"
    if "CADASTR" in p or "PROPERTY" in p or "INVARIANT" in p:
        return "PROPERTY_REF"
    if "EMAIL" in p:
        return "EMAIL"
    if "PHONE" in p or "TELEPHONE" in p:
        return "PHONE"
    if "DATE" in p:
        return "DATE"
    if "NSS" in p or "SECU" in p:
        return "SOCIAL_SECURITY"
    if "MONTANT" in p or "AMOUNT" in p:
        return "AMOUNT"
    if "FACTURE" in p or "INVOICE" in p or "REF_FACTURE" in p:
        return "INVOICE_REF"
    return "OTHER"


# ── Document access ───────────────────────────────────────────────────


async def _get_user_document_or_404(
    db: AsyncSession,
    document_id: str,
    user_id: uuid.UUID,
    permission: str = "documents.read",
) -> Document:
    try:
        document_uuid = uuid.UUID(document_id)
    except ValueError as exc:
        raise http_404("Document introuvable") from exc

    active_org_ids = await user_active_org_ids(db, user_id)
    ownership_filters = [Document.uploaded_by_user_id == user_id]
    if active_org_ids:
        ownership_filters.append(Document.org_id.in_(active_org_ids))

    result = await db.execute(
        select(Document).where(
            Document.id == document_uuid,
            or_(*ownership_filters),
            Document.is_deleted.is_(False),
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise http_404("Document introuvable")
    await require_document_permission(
        db,
        user_id=user_id,
        document=document,
        permission=permission,
    )
    return document


def _read_file_or_404(document: Document) -> bytes:
    from app.services.storage_service import read_document_bytes

    try:
        return read_document_bytes(document)
    except Exception as exc:
        logger.warning("document_source_read_failed", doc_id=str(document.id), error=str(exc))

    raise http_404("Fichier source introuvable. Ré-uploadez le document.")


async def _get_or_create_final_version(db: AsyncSession, document: Document) -> DocumentVersion:
    result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.FINAL_ANONYMIZED,
        )
    )
    final = result.scalar_one_or_none()
    if final:
        return final

    preview_result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.PREVIEW_ANONYMIZED,
        )
    )
    preview = preview_result.scalar_one_or_none()
    if not preview:
        raise http_404("Aucune version anonymisée disponible. Lancez d'abord l'anonymisation.")

    final = DocumentVersion(
        document_id=document.id,
        version_type=DocumentVersionType.FINAL_ANONYMIZED,
        content_text=postgres_safe_text(preview.content_text),
    )
    db.add(final)
    await db.flush()
    return final


async def _get_original_text(db: AsyncSession, document: Document) -> str:
    from app.services.anonymization_service import extract_text_from_file

    result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.ORIGINAL_TEXT,
        )
    )
    version = result.scalar_one_or_none()
    if version and version.content_text:
        return version.content_text

    file_content = _read_file_or_404(document)
    return await extract_text_from_file(file_content, document.extension) or ""


async def _get_anonymized_text(db: AsyncSession, document: Document) -> str:
    """Get best anonymized text (final > preview)."""
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


async def _check_export_gate(db: AsyncSession, document: Document, current_user: object) -> None:
    """Enforce RGPD export policy based on risk level."""
    doc_id = str(document.id)
    user_id = str(getattr(current_user, "id", "unknown"))
    try:
        from app.models.pseudonym_mapping import PseudonymMapping

        result = await db.execute(
            select(PseudonymMapping)
            .where(PseudonymMapping.document_id == document.id)
            .order_by(PseudonymMapping.created_at.desc())
            .limit(1)
        )
        mapping = result.scalar_one_or_none()

        if not mapping:
            return

        risk_level = mapping.risk_level or "low"

        if risk_level == "critical":
            raise http_400(
                "Export bloqué : risque de réidentification critique. "
                "Renforcez l'anonymisation avant d'exporter."
            )

        if risk_level == "high" and not mapping.human_validated:
            raise http_400(
                "Export bloqué : risque élevé. "
                "Une validation humaine est requise avant export. "
                "Utilisez POST /documents/{id}/approve-export."
            )

        if risk_level == "medium":
            logger.warning(
                "export_medium_risk",
                doc_id=doc_id,
                user_id=user_id,
                risk_score=mapping.risk_score,
            )
    except Exception as exc:
        if hasattr(exc, "status_code"):
            raise
        logger.error(
            "export_gate_check_failed",
            doc_id=doc_id,
            user_id=user_id,
            error=str(exc),
        )
        raise http_400(
            "Export temporairement indisponible : controle de conformite inaccessible."
        ) from exc
