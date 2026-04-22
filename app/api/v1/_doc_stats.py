"""ConfiDoc — Documents stats endpoints.

Routes : /stats/dashboard, /status-summary.
Ces routes sont statiques et doivent être déclarées AVANT /{document_id}.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import desc, func, select

from app.api.deps import CurrentUser, DbSession
from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.models.document import Document, DocumentStatus
from app.models.entity_detection import EntityDetection
from app.services.dossier_360_service import build_dossier_360

router = APIRouter()
logger = get_logger(__name__)


def _calculate_gdpr_score(
    total_docs: int,
    status_counts: dict,
    risk_distribution: dict,
    recent_activity: list,
) -> dict:
    """Calcule un score de readiness RGPD (0–100) avec recommandations."""
    ready = status_counts.get("ready", 0)
    failed = status_counts.get("failed", 0)
    processing = status_counts.get("processing", 0)
    uploaded = status_counts.get("uploaded", 0)

    success_rate = (ready / total_docs * 40) if total_docs else 0

    total_risks = sum(risk_distribution.values())
    if total_risks:
        risk_pts = (
            risk_distribution.get("low", 0) * 1.0
            + risk_distribution.get("medium", 0) * 0.7
            + risk_distribution.get("high", 0) * 0.3
            + risk_distribution.get("critical", 0) * 0.0
        ) / total_risks * 30
    else:
        risk_pts = 30

    failure_rate = (failed / total_docs) if total_docs else 0
    failure_pts = max(0, 15 - int(failure_rate * 30))

    recent_count = sum(a.get("count", 0) for a in recent_activity)
    activity_pts = min(10, recent_count)

    pending = processing + uploaded
    pending_pts = max(0, 5 - int((pending / max(total_docs, 1)) * 5))

    total = min(100, int(success_rate + risk_pts + failure_pts + activity_pts + pending_pts))

    if total >= 85:
        grade, status_label, color = "A", "Conforme", "success"
    elif total >= 70:
        grade, status_label, color = "B", "A améliorer", "warning"
    else:
        grade, status_label, color = "C" if total >= 50 else "D", "Non conforme", "danger"

    recommendations = []
    if failure_rate > 0.1:
        recommendations.append(
            "Plusieurs documents sont en échec. Vérifiez la qualité des fichiers sources."
        )
    if pending > 3:
        recommendations.append(f"{pending} documents sont en attente. Lancez l'analyse.")
    if risk_distribution.get("high", 0) + risk_distribution.get("critical", 0) > total_risks * 0.2:
        recommendations.append("Trop de mappings à haut risque. Validez manuellement les exports.")
    if ready == 0 and total_docs > 0:
        recommendations.append("Aucun document anonymisé. Lancez le traitement IA.")
    if not recommendations:
        recommendations.append(
            "Votre posture RGPD est bonne. Continuez à valider les exports à risque élevé."
        )

    return {
        "score": total,
        "grade": grade,
        "status": status_label,
        "color": color,
        "breakdown": {
            "success_rate": round(success_rate, 1),
            "risk_score": round(risk_pts, 1),
            "failure_resilience": round(failure_pts, 1),
            "activity_momentum": round(activity_pts, 1),
            "pending_penalty": round(pending_pts, 1),
        },
        "recommendations": recommendations,
    }


@router.get(
    "/golden-report",
    status_code=status.HTTP_200_OK,
    summary="Récupérer le dernier rapport de non-régression (Golden Sets)",
)
async def get_golden_report(current_user: CurrentUser) -> dict:
    """Sert le rapport JSON généré par scripts/run_golden_v2.py."""
    import os
    # On cherche golden/latest_quality_report.json dans le root du projet
    root = os.getcwd()
    report_path = os.path.join(root, "golden", "latest_quality_report.json")
    
    if not os.path.exists(report_path):
        return {
            "status": "no_report",
            "message": "Aucun rapport généré. Lancez 'make golden' d'abord.",
            "metrics": {
                "pass_rate": 0,
                "total": 0,
                "passed": 0,
                "failed": 0
            }
        }
        
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (IOError, ValueError, json.JSONDecodeError) as exc:
        logger.error("golden_report_read_failed", error=str(exc))
        return {"status": "error", "message": str(exc)}


@router.get(
    "/stats/dashboard",
    status_code=status.HTTP_200_OK,
    summary="Statistiques dashboard utilisateur",
)
async def get_dashboard_stats(
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    user_id = current_user.id

    result = await db.execute(
        select(Document.status, func.count())
        .where(
            Document.uploaded_by_user_id == user_id,
            Document.is_deleted.is_(False),
        )
        .group_by(Document.status)
    )
    status_counts = {
        row[0].value if hasattr(row[0], "value") else str(row[0]): row[1]
        for row in result.all()
    }
    total_docs = sum(status_counts.values())

    risk_distribution = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    try:
        from app.models.pseudonym_mapping import PseudonymMapping
        async with async_session_factory() as db2:
            risk_result = await db2.execute(
                select(PseudonymMapping.risk_level, func.count())
                .where(PseudonymMapping.user_id == user_id)
                .group_by(PseudonymMapping.risk_level)
            )
            for row in risk_result.all():
                level = row[0] or "low"
                if level in risk_distribution:
                    risk_distribution[level] = row[1]
    except __import__("sqlalchemy").exc.SQLAlchemyError:
        pass

    entity_distribution: dict[str, int] = {}
    try:
        async with async_session_factory() as db2:
            doc_ids_result = await db2.execute(
                select(Document.id).where(
                    Document.uploaded_by_user_id == user_id,
                    Document.is_deleted.is_(False),
                )
            )
            doc_ids = [row[0] for row in doc_ids_result.all()]
            if doc_ids:
                ent_result = await db2.execute(
                    select(EntityDetection.entity_type, func.count())
                    .where(EntityDetection.document_id.in_(doc_ids))
                    .group_by(EntityDetection.entity_type)
                )
                entity_distribution = {(row[0] or "unknown"): row[1] for row in ent_result.all()}
    except __import__("sqlalchemy").exc.SQLAlchemyError:
        pass

    recent_activity: list[dict] = []
    try:
        from app.models.audit_log import AuditLog
        since = datetime.now(UTC) - timedelta(days=7)
        async with async_session_factory() as db2:
            activity_result = await db2.execute(
                select(
                    func.date_trunc("day", AuditLog.created_at).label("day"),
                    func.count(),
                )
                .where(AuditLog.user_id == user_id, AuditLog.created_at >= since)
                .group_by("day")
                .order_by("day")
            )
            recent_activity = [
                {"date": row[0].isoformat() if row[0] else "", "count": row[1]}
                for row in activity_result.all()
            ]
    except __import__("sqlalchemy").exc.SQLAlchemyError:
        pass

    trash_result = await db.execute(
        select(func.count()).select_from(Document).where(
            Document.uploaded_by_user_id == user_id,
            Document.is_deleted.is_(True),
        )
    )
    trashed = trash_result.scalar() or 0
    total_entities = sum(entity_distribution.values())

    # ── KPIs Investor-Ready ──
    # Processing time median (uploaded → ready)
    processing_stats = {"avg_seconds": None, "median_seconds": None}
    try:
        from sqlalchemy import func as sa_func
        time_result = await db.execute(
            select(
                sa_func.avg(
                    sa_func.extract("epoch", Document.updated_at - Document.created_at)
                ),
                sa_func.percentile_cont(0.5).within_group(
                    sa_func.extract("epoch", Document.updated_at - Document.created_at)
                ),
            )
            .where(
                Document.uploaded_by_user_id == user_id,
                Document.is_deleted.is_(False),
                Document.status == DocumentStatus.READY,
                Document.updated_at > Document.created_at,
            )
        )
        row = time_result.one_or_none()
        if row:
            processing_stats["avg_seconds"] = round(row[0], 1) if row[0] else None
            processing_stats["median_seconds"] = round(row[1], 1) if row[1] else None
    except __import__("sqlalchemy").exc.SQLAlchemyError:
        pass

    # Document type distribution
    doc_type_dist: dict[str, int] = {}
    try:
        type_result = await db.execute(
            select(Document.doc_type, func.count())
            .where(
                Document.uploaded_by_user_id == user_id,
                Document.is_deleted.is_(False),
                Document.doc_type.isnot(None),
            )
            .group_by(Document.doc_type)
        )
        doc_type_dist = {row[0] or "unknown": row[1] for row in type_result.all()}
    except __import__("sqlalchemy").exc.SQLAlchemyError:
        pass

    return {
        "total_documents": total_docs,
        "status_counts": status_counts,
        "risk_distribution": risk_distribution,
        "entity_distribution": entity_distribution,
        "total_entities_masked": total_entities,
        "recent_activity": recent_activity,
        "trashed_documents": trashed,
        "processing_time": processing_stats,
        "document_type_distribution": doc_type_dist,
        "gdpr_score": _calculate_gdpr_score(
            total_docs,
            status_counts,
            risk_distribution,
            recent_activity,
        ),
    }


async def _load_dossier_360_payload(
    current_user: CurrentUser,
    db: DbSession,
    limit: int,
) -> dict:
    user_id = current_user.id
    result = await db.execute(
        select(Document)
        .where(
            Document.uploaded_by_user_id == user_id,
            Document.is_deleted.is_(False),
        )
        .order_by(desc(Document.updated_at))
        .limit(500)
    )
    docs = list(result.scalars().all())
    doc_ids = [doc.id for doc in docs]

    risk_by_document: dict[str, float] = {}
    if doc_ids:
        try:
            from app.models.pseudonym_mapping import PseudonymMapping

            risk_result = await db.execute(
                select(PseudonymMapping.document_id, func.max(PseudonymMapping.risk_score))
                .where(
                    PseudonymMapping.user_id == user_id,
                    PseudonymMapping.document_id.in_(doc_ids),
                )
                .group_by(PseudonymMapping.document_id)
            )
            risk_by_document = {
                str(row[0]): float(row[1] or 0.0)
                for row in risk_result.all()
            }
        except __import__("sqlalchemy").exc.SQLAlchemyError as exc:
            logger.warning("dossier_360_risk_failed", error=str(exc))

    entity_counts_by_document: dict[str, int] = {}
    if doc_ids:
        try:
            entity_result = await db.execute(
                select(EntityDetection.document_id, func.count())
                .where(EntityDetection.document_id.in_(doc_ids))
                .group_by(EntityDetection.document_id)
            )
            entity_counts_by_document = {
                str(row[0]): int(row[1] or 0)
                for row in entity_result.all()
            }
        except __import__("sqlalchemy").exc.SQLAlchemyError as exc:
            logger.warning("dossier_360_entities_failed", error=str(exc))

    payload = [
        {
            "id": doc.id,
            "original_filename": doc.original_filename,
            "status": doc.status,
            "doc_type": doc.doc_type,
            "tags": doc.tags or [],
            "created_at": doc.created_at.isoformat() if doc.created_at else "",
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else "",
        }
        for doc in docs
    ]
    return build_dossier_360(
        payload,
        risk_by_document=risk_by_document,
        entity_counts_by_document=entity_counts_by_document,
        limit=limit,
    )


@router.get(
    "/stats/dossier-360",
    status_code=status.HTTP_200_OK,
    summary="Vue Dossier 360 par client",
)
async def get_dossier_360_stats(
    current_user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=6, ge=1, le=20),
) -> dict:
    return await _load_dossier_360_payload(current_user, db, limit)


@router.get(
    "/stats/dossier-360/report",
    status_code=status.HTTP_200_OK,
    summary="Rapport PDF Dossier 360",
)
async def get_dossier_360_report_pdf(
    current_user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=8, ge=1, le=30),
) -> Response:
    from app.services.pdf_dossier_360_report_service import generate_dossier_360_pdf

    payload = await _load_dossier_360_payload(current_user, db, limit)
    pdf_bytes = generate_dossier_360_pdf(payload)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="rapport_dossier_360.pdf"'},
    )


@router.get(
    "/status-summary",
    status_code=status.HTTP_200_OK,
    summary="Résumé des statuts sur une période",
)
async def get_documents_status_summary(
    current_user: CurrentUser,
    db: DbSession,
    days: int = Query(default=30, ge=1, le=365),
) -> dict:
    user_id = current_user.id
    now = datetime.now(UTC)
    since = now - timedelta(days=days)
    last_24h = now - timedelta(hours=24)

    result = await db.execute(
        select(Document.status, func.count())
        .where(
            Document.uploaded_by_user_id == user_id,
            Document.is_deleted.is_(False),
            Document.created_at >= since,
        )
        .group_by(Document.status)
    )
    status_counts: dict[str, int] = {}
    for row in result.all():
        st = row[0]
        key = st.value if hasattr(st, "value") else str(st)
        status_counts[key] = row[1]

    total_documents = sum(status_counts.values())

    recent_result = await db.execute(
        select(func.count()).select_from(Document).where(
            Document.uploaded_by_user_id == user_id,
            Document.is_deleted.is_(False),
            Document.created_at >= last_24h,
        )
    )
    recent_uploads_24h = recent_result.scalar() or 0

    buckets = {
        "full_ready": {
            "status": DocumentStatus.READY.value,
            "label": "Prêt (anonymisation complète)",
            "count": status_counts.get(DocumentStatus.READY.value, 0),
        },
        "processing": {
            "status": DocumentStatus.PROCESSING.value,
            "label": "En traitement",
            "count": status_counts.get(DocumentStatus.PROCESSING.value, 0),
        },
        "uploaded": {
            "status": DocumentStatus.UPLOADED.value,
            "label": "Téléversé",
            "count": status_counts.get(DocumentStatus.UPLOADED.value, 0),
        },
        "failed": {
            "status": DocumentStatus.FAILED.value,
            "label": "Échec",
            "count": status_counts.get(DocumentStatus.FAILED.value, 0),
        },
    }

    return {
        "period_days": days,
        "total_documents": total_documents,
        "buckets": buckets,
        "status_counts": status_counts,
        "recent_uploads_24h": recent_uploads_24h,
        "last_updated": now.isoformat(),
    }
