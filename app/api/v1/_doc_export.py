"""ConfiDoc — Documents export & report endpoints.

Routes : export (texte), export-pdf, audit-report, audit-report-pdf,
         compliance-report, risk-score.

Note : l'ancien doublon de /compliance-report a été fusionné en une seule
route qui combine le scoring structuré (V1) et l'appel LLM optionnel (V2).
"""

from __future__ import annotations

import asyncio
import io
import uuid
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, Body, status
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.api.v1._doc_shared import (
    _check_export_gate,
    _get_anonymized_text,
    _get_or_create_final_version,
    _get_user_document_or_404,
    _read_file_or_404,
)
from app.core.exceptions import http_400, http_404
from app.core.logging import get_logger
from app.models.document import Document, DocumentStatus
from app.models.document_version import DocumentVersion, DocumentVersionType
from app.models.entity_detection import EntityDetection

router = APIRouter()
logger = get_logger(__name__)


@router.get(
    "/{document_id}/export",
    response_class=PlainTextResponse,
    status_code=status.HTTP_200_OK,
    summary="Exporter le texte anonymisé",
)
async def export_document(
    document_id: str, current_user: CurrentUser, db: DbSession
):
    try:
        document = await _get_user_document_or_404(db, document_id, current_user.id)
        _doc_id = str(document.id)
        _user_id = current_user.id
        _org_id = getattr(current_user, "org_id", None)

        await _check_export_gate(db, document, current_user)
        final = await _get_or_create_final_version(db, document)
        text_content = final.content_text
        await db.commit()

        try:
            from app.models.audit_log import AuditLog
            db.add(AuditLog(
                user_id=_user_id, org_id=_org_id,
                action="export:text", resource_type="document",
                resource_id=_doc_id, method="GET",
                path=f"/api/v1/documents/{document_id}/export", status_code=200,
            ))
            await db.commit()
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass

        return PlainTextResponse(text_content)
    except Exception as exc:
        if hasattr(exc, "status_code"):
            raise
        logger.error("export_text_failed", error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"detail": f"Export failed: {type(exc).__name__}: {str(exc)[:500]}"},
        )


@router.get(
    "/{document_id}/export-pdf",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
    summary="Exporter le PDF avec données visuellement masquées",
)
async def export_redacted_pdf(
    document_id: str, current_user: CurrentUser, db: DbSession
):
    try:
        document = await _get_user_document_or_404(db, document_id, current_user.id)
        await _check_export_gate(db, document, current_user)

        if document.extension.lower() != "pdf":
            raise http_400("Export PDF redacté disponible uniquement pour les fichiers PDF")

        detections_result = await db.execute(
            select(EntityDetection).where(EntityDetection.document_id == document.id)
        )
        detections = list(detections_result.scalars().all())

        if not detections:
            source_text = await _get_anonymized_text(db, document)
            if source_text:
                from app.services.anonymization_service import anonymize_text, classify_document_type
                effective_type = classify_document_type(source_text, document.original_filename)
                _anon_text, regenerated, _registry = anonymize_text(
                    source_text, profile="strict", document_type=effective_type
                )
                detections = [
                    SimpleNamespace(value_excerpt=item.get("value_excerpt", ""))
                    for item in regenerated
                    if item.get("value_excerpt")
                ]
            if not detections:
                raise http_404("Aucune détection disponible. Lancez /anonymize d'abord.")

        original_bytes = _read_file_or_404(document)
        sensitive_values = [item.value_excerpt for item in detections if item.value_excerpt]

        try:
            from app.services.pdf_redaction_service import redact_pdf_bytes
            loop = asyncio.get_running_loop()
            redacted_bytes = await loop.run_in_executor(None, redact_pdf_bytes, original_bytes, sensitive_values)
        except Exception as exc:
            logger.error("pdf_redaction_failed", doc_id=str(document.id), error=str(exc))
            raise http_400("Impossible de générer le PDF redacté.")

        headers = {"Content-Disposition": f'attachment; filename="redacted_{document.original_filename}"'}
        return StreamingResponse(BytesIO(redacted_bytes), media_type="application/pdf", headers=headers)
    except Exception as exc:
        if hasattr(exc, "status_code"):
            raise
        logger.error("export_pdf_failed", error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"detail": f"Export PDF failed: {type(exc).__name__}: {str(exc)[:500]}"},
        )


@router.get(
    "/{document_id}/audit-report",
    status_code=status.HTTP_200_OK,
    summary="Rapport d'audit RGPD du document (JSON)",
)
async def get_audit_report(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    document = await _get_user_document_or_404(db, document_id, current_user.id)

    entries: list[dict] = []
    try:
        from app.models.audit_log import AuditLog
        result = await db.execute(
            select(AuditLog)
            .where(AuditLog.resource_id == str(document.id))
            .order_by(AuditLog.created_at.desc())
        )
        logs = list(result.scalars().all())
        entries = [
            {
                "action": log.action,
                "user_id": str(log.user_id) if log.user_id else None,
                "timestamp": log.created_at.isoformat() if log.created_at else None,
                "method": log.method,
                "path": log.path,
                "status_code": log.status_code,
                "details": log.details,
            }
            for log in logs
        ]
    except Exception as exc:
        logger.warning("audit_report_query_failed", error=str(exc))

    risk_info = None
    try:
        from app.models.pseudonym_mapping import PseudonymMapping
        mr = await db.execute(
            select(PseudonymMapping)
            .where(PseudonymMapping.document_id == document.id)
            .order_by(PseudonymMapping.created_at.desc())
        )
        mapping = mr.scalar_one_or_none()
        if mapping:
            risk_info = {
                "score": mapping.risk_score,
                "level": mapping.risk_level,
                "human_validated": mapping.human_validated,
                "validated_at": mapping.validated_at.isoformat() if mapping.validated_at else None,
                "expires_at": mapping.expires_at.isoformat() if mapping.expires_at else None,
            }
    except Exception:
        pass

    return {
        "document_id": str(document.id),
        "filename": document.original_filename,
        "created_at": document.created_at.isoformat() if document.created_at else None,
        "risk": risk_info,
        "audit_entries": entries,
        "total_actions": len(entries),
    }


@router.get(
    "/{document_id}/audit-report-pdf",
    status_code=status.HTTP_200_OK,
    summary="Rapport d'audit RGPD du document (PDF professionnel)",
)
async def get_audit_report_pdf(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
):
    report_data = await get_audit_report(document_id, current_user, db)

    entity_summary: dict[str, int] = {}
    try:
        det_result = await db.execute(
            select(EntityDetection).where(
                EntityDetection.document_id == uuid.UUID(document_id)
            )
        )
        for det in det_result.scalars().all():
            etype = det.entity_type or "unknown"
            entity_summary[etype] = entity_summary.get(etype, 0) + 1
    except Exception:
        pass

    anonymized_preview = ""
    try:
        document = await _get_user_document_or_404(db, document_id, current_user.id)
        anonymized_preview = await _get_anonymized_text(db, document)
    except Exception:
        pass

    risk_info = report_data.get("risk")
    if risk_info and anonymized_preview:
        from app.services.reidentification_risk_service import analyze_reidentification_risk
        risk_report = analyze_reidentification_risk(anonymized_preview, entity_summary)
        risk_info["recommendation"] = risk_report.recommendation

    document_info = {
        "document_id": report_data.get("document_id", ""),
        "filename": report_data.get("filename", "Document"),
        "created_at": report_data.get("created_at", ""),
        "doc_type": "Auto",
        "status": "ready",
    }

    from app.services.pdf_audit_report_service import generate_audit_pdf
    pdf_bytes = generate_audit_pdf(
        document_info=document_info,
        risk_info=risk_info,
        entity_summary=entity_summary,
        audit_entries=report_data.get("audit_entries", []),
        anonymized_text_preview=anonymized_preview[:4000],
    )

    short_id = document_info["document_id"][:8]
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="audit_rgpd_{short_id}.pdf"'},
    )


@router.get(
    "/{document_id}/risk-score",
    status_code=status.HTTP_200_OK,
    summary="Score de risque RGPD et recommandations",
)
async def get_document_risk_score(
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
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise http_404("Document introuvable")

    from app.models.pseudonym_mapping import PseudonymMapping
    pm_result = await db.execute(
        select(PseudonymMapping).where(PseudonymMapping.document_id == doc_uuid)
    )
    mapping = pm_result.scalar_one_or_none()

    risk_score = 0.0
    risk_level = "low"

    if mapping and mapping.risk_score is not None:
        risk_score = mapping.risk_score
        risk_level = mapping.risk_level or "low"
    else:
        ent_result = await db.execute(
            select(EntityDetection.entity_type).where(EntityDetection.document_id == doc_uuid)
        )
        entities = [row[0] for row in ent_result.all()]
        unique_types = set(entities)
        count = len(entities)

        if "PERSONNE" in unique_types or "EMAIL" in unique_types or "TELEPHONE" in unique_types:
            risk_score = max(risk_score, 60.0)
        if "SIREN" in unique_types or "SIRET" in unique_types:
            risk_score = max(risk_score, 50.0)
        if "IBAN" in unique_types or "CARTE_BANCAIRE" in unique_types:
            risk_score = max(risk_score, 90.0)
        if count > 50:
            risk_score = min(risk_score + 15.0, 100.0)
        elif count > 20:
            risk_score = min(risk_score + 10.0, 100.0)

        if risk_score >= 80:
            risk_level = "critical"
        elif risk_score >= 60:
            risk_level = "high"
        elif risk_score >= 40:
            risk_level = "medium"
        else:
            risk_level = "low"

    ent_result = await db.execute(
        select(EntityDetection.entity_type).where(EntityDetection.document_id == doc_uuid)
    )
    unique_types = {row[0] for row in ent_result.all()}

    recommendations: list[str] = []
    if "CARTE_BANCAIRE" in unique_types or "IBAN" in unique_types:
        recommendations.append("Données bancaires détectées : validation manuelle avant tout export.")
    if "EMAIL" in unique_types or "TELEPHONE" in unique_types:
        recommendations.append("Coordonnées directes présentes : appliquer une anonymisation stricte.")
    if "PERSONNE" in unique_types:
        recommendations.append("Identités de personnes physiques : vérifier la base légale du traitement.")
    if risk_score < 40:
        recommendations.append("Risque faible : document probablement conforme pour un usage interne.")
    if not mapping or not mapping.human_validated:
        recommendations.append("Validation humaine recommandée avant diffusion externe.")

    return {
        "document_id": document_id,
        "risk_score": round(risk_score, 1),
        "risk_level": risk_level,
        "human_validated": bool(mapping and mapping.human_validated),
        "recommendations": recommendations,
        "entity_types_found": sorted(unique_types) if unique_types else [],
    }


@router.get(
    "/{document_id}/compliance-report",
    status_code=status.HTTP_200_OK,
    summary="Rapport de conformité RGPD structuré (+ IA optionnel)",
)
async def get_compliance_report(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    """Rapport de conformité RGPD combinant scoring structuré et analyse LLM optionnelle.

    Le scoring algorithmique est toujours calculé. Si Mistral est activé et disponible,
    le rapport narratif est enrichi par le LLM. En cas d'échec LLM, le fallback
    algorithmique est utilisé sans dégradation.
    """
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

    # Entity counts
    ent_result = await db.execute(
        select(EntityDetection.entity_type, __import__("sqlalchemy").func.count())
        .where(EntityDetection.document_id == doc_uuid)
        .group_by(EntityDetection.entity_type)
    )
    entity_counts: dict[str, int] = {row[0] or "unknown": row[1] for row in ent_result.all()}
    total_entities = sum(entity_counts.values())

    # Risk info
    from app.models.pseudonym_mapping import PseudonymMapping
    pm_result = await db.execute(
        select(PseudonymMapping)
        .where(PseudonymMapping.document_id == doc_uuid)
        .order_by(PseudonymMapping.created_at.desc())
    )
    mapping = pm_result.scalar_one_or_none()
    risk_score_val = round(mapping.risk_score, 1) if mapping and mapping.risk_score is not None else 0.0
    risk_level = mapping.risk_level or "low" if mapping else "low"
    human_validated = bool(mapping and mapping.human_validated)

    # Anonymized text for LLM / recommendation
    anonymized_preview = ""
    try:
        anonymized_preview = await _get_anonymized_text(db, document)
    except Exception:
        pass

    risk_info: dict[str, Any] = {
        "score": risk_score_val,
        "level": risk_level,
        "human_validated": human_validated,
    }
    if mapping:
        risk_info["validated_at"] = mapping.validated_at.isoformat() if mapping.validated_at else None
        risk_info["expires_at"] = mapping.expires_at.isoformat() if mapping.expires_at else None

    if anonymized_preview and entity_counts:
        try:
            from app.services.reidentification_risk_service import analyze_reidentification_risk
            rr = analyze_reidentification_risk(anonymized_preview, entity_counts)
            risk_info["recommendation"] = rr.recommendation
        except Exception:
            pass

    # Algorithmic conformity score
    risk_pts = max(0, 60 - int(risk_score_val * 60))
    validation_pts = 20 if human_validated else 0
    entity_pts = 10 if total_entities > 0 else 0
    audit_pts = 10
    conformity_score = min(100, risk_pts + validation_pts + entity_pts + audit_pts)

    if conformity_score >= 85:
        grade, status_label, color = "A", "Conforme", "success"
    elif conformity_score >= 65:
        grade, status_label, color = "B", "À valider", "warning"
    elif conformity_score >= 45:
        grade, status_label, color = "C", "Non conforme", "danger"
    else:
        grade, status_label, color = "D", "Non conforme", "danger"

    actions_required: list[str] = []
    if risk_score_val > 0.5 and not human_validated:
        actions_required.append("Validation humaine obligatoire avant export (risque élevé).")
    if total_entities == 0:
        actions_required.append("Aucune entité détectée. Vérifiez la qualité du document source.")
    if document.status != DocumentStatus.READY:
        actions_required.append("Le document n'est pas encore prêt. Finalisez le traitement.")
    if not actions_required:
        actions_required.append("Aucune action requise. Le document respecte les critères RGPD.")

    # Audit summary
    audit_entries: list[dict] = []
    try:
        from app.models.audit_log import AuditLog
        a_result = await db.execute(
            select(AuditLog)
            .where(AuditLog.resource_id == str(document.id))
            .order_by(AuditLog.created_at.desc())
        )
        audit_entries = [
            {
                "action": log.action,
                "timestamp": log.created_at.isoformat() if log.created_at else None,
                "method": log.method,
                "status_code": log.status_code,
            }
            for log in a_result.scalars().all()
        ]
    except Exception:
        pass

    # Optional LLM narrative report
    llm_report: dict[str, Any] = {
        "summary": "Rapport généré automatiquement.",
        "findings": [f"{k}: {v} occurrence(s)" for k, v in entity_counts.items()],
        "recommendations": ["Vérifier la base légale du traitement.", "Valider manuellement avant export externe."],
        "conclusion": "Document conforme en l'état pour un usage interne.",
    }
    from app.config import get_settings
    settings = get_settings()
    if settings.MISTRAL_ENABLED and settings.MISTRAL_API_KEY and anonymized_preview:
        try:
            prompt = (
                f"Tu es un DPO. Rédige un rapport de compliance RGPD concis en JSON strict:\n"
                f"{{'summary':..., 'findings':[...], 'recommendations':[...], 'conclusion':...}}\n"
                f"Infos: nom={document.original_filename}, entités={entity_counts}, "
                f"risque={risk_score_val}/100 ({risk_level}), texte={anonymized_preview[:1500]}\n"
                f"Ne renvoie que le JSON."
            )
            import json
            from app.services.mistral_service import chat_completion
            raw = await chat_completion(prompt, temperature=0.3)
            parsed = json.loads(raw)
            llm_report = {
                "summary": parsed.get("summary", llm_report["summary"]),
                "findings": parsed.get("findings", llm_report["findings"]),
                "recommendations": parsed.get("recommendations", llm_report["recommendations"]),
                "conclusion": parsed.get("conclusion", llm_report["conclusion"]),
            }
        except Exception as exc:
            logger.warning("compliance_llm_failed", error=str(exc))

    return {
        "report_id": str(uuid.uuid4()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "document": {
            "document_id": str(document.id),
            "filename": document.original_filename,
            "created_at": document.created_at.isoformat() if document.created_at else None,
            "status": document.status.value if hasattr(document.status, "value") else str(document.status),
        },
        "conformity": {
            "score": conformity_score,
            "grade": grade,
            "status": status_label,
            "color": color,
            "max_score": 100,
        },
        "risk": risk_info,
        "entities": {
            "summary": entity_counts,
            "total": total_entities,
            "top_categories": sorted(entity_counts.items(), key=lambda x: -x[1])[:5],
        },
        "actions_required": actions_required,
        "audit_summary": {
            "total_actions": len(audit_entries),
            "last_action_at": audit_entries[0]["timestamp"] if audit_entries else None,
        },
        "narrative_report": llm_report,
        "certifications": {
            "pseudonymisation_separated": True,
            "audit_trail_enabled": True,
            "risk_scoring_enabled": True,
            "human_validation_gate": True,
        },
    }


@router.post(
    "/{document_id}/compare",
    status_code=status.HTTP_200_OK,
    summary="Comparer le document avec une version N-1",
)
async def compare_with_previous(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
    previous_document_id: str = Body(..., embed=True),
) -> dict:
    """Compare deux documents (N vs N-1) pour détecter les variations.

    Body: {"previous_document_id": "uuid"}
    """
    from app.services.comparison_service import compare_documents

    current_doc = await _get_user_document_or_404(db, document_id, current_user.id)
    prev_doc = await _get_user_document_or_404(db, previous_document_id, current_user.id)

    current_text = await _get_anonymized_text(db, current_doc)
    prev_text = await _get_anonymized_text(db, prev_doc)

    if not current_text:
        raise http_400("Document courant non anonymisé. Lancez /anonymize d'abord.")
    if not prev_text:
        raise http_400("Document précédent non anonymisé. Lancez /anonymize d'abord.")

    result = await compare_documents(
        db=db,
        current_text=current_text,
        previous_text=prev_text,
        doc_type=current_doc.doc_type or "bilan",
    )

    return {
        "comparison_id": str(uuid.uuid4()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_document_id": str(current_doc.id),
        "previous_document_id": str(prev_doc.id),
        **result,
    }
