"""ConfiDoc — Documents stats endpoints.

Routes supportées (compatibilité UI) :
- /api/v1/stats/dashboard
- /api/v1/documents/status-summary
- /api/v1/documents/stats/dashboard
- /api/v1/stats/golden-report
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import desc, func, select

from app.api.deps import CurrentUser, DbSession
from app.core.logging import get_logger
from app.models.document import Document
from app.models.entity_detection import EntityDetection
from app.models.pseudonym_mapping import PseudonymMapping
from app.schemas.quality_metrics import QualityDashboardResponse
from app.services.dossier_360_service import build_dossier_360
from app.services.quality_metrics_service import compute_quality_metrics
from app.services.trust_score_service import compute_portfolio_trust_score

router = APIRouter()
logger = get_logger(__name__)


def _risk_score_percent(score: float | int | None) -> float:
    if score is None:
        return 0.0
    value = float(score)
    if 0 <= value <= 1:
        value *= 100
    return max(0.0, min(100.0, value))


def _status_key(status: object) -> str:
    return str(getattr(status, "value", status) or "").strip().lower()


def _document_to_dossier_360_input(document: Document) -> dict[str, Any]:
    tags = list(getattr(document, "tags", None) or [])
    client_name = str(getattr(document, "client_name", "") or "").strip()
    if client_name and client_name not in tags:
        tags = [client_name, *tags]

    doc_category = getattr(document, "doc_category", None)
    doc_type = getattr(document, "doc_type", None) or doc_category
    return {
        "id": getattr(document, "id", ""),
        "original_filename": getattr(document, "original_filename", ""),
        "status": getattr(document, "status", ""),
        "tags": tags,
        "client_name": client_name or None,
        "doc_type": doc_type,
        "doc_category": doc_category,
        "exercice": getattr(document, "exercice", None),
        "created_at": getattr(document, "created_at", None),
        "updated_at": getattr(document, "updated_at", None),
    }


def _created_last_7_days(created_values: list[datetime], now: datetime) -> list[dict[str, Any]]:
    buckets = {
        (now.date() - timedelta(days=offset)): 0
        for offset in range(6, -1, -1)
    }
    for created_at in created_values:
        if created_at is None:
            continue
        day = created_at.date()
        if day in buckets:
            buckets[day] += 1
    return [{"date": day.isoformat(), "count": count} for day, count in buckets.items()]


def _calculate_gdpr_score(
    total_docs: int,
    status_counts: dict,
    risk_distribution: dict,
    recent_activity: list,
) -> dict:
    """Calcule un score de readiness RGPD (0–100) avec recommandations."""
    if total_docs <= 0:
        # Sans pièce, aucun agrégat réel : ne pas inventer un score / une « note » (risque produit).
        return {
            "score": None,
            "grade": None,
            "status": "Score RGPD non disponible",
            "color": "neutral",
            "breakdown": {},
            "recommendations": [
                "Ajoutez un premier document pour calculer votre posture RGPD.",
            ],
        }

    ready = status_counts.get("ready", 0) + status_counts.get("anonymized", 0)
    failed = status_counts.get("failed", 0)
    processing = (
        status_counts.get("processing", 0)
        + status_counts.get("extracting", 0)
        + status_counts.get("extracted", 0)
        + status_counts.get("anonymizing", 0)
    )
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
    summary="Récupérer le dernier rapport de non-régression",
)
@router.get(
    "/stats/golden-report",
    include_in_schema=False,
)
async def get_golden_report(current_user: CurrentUser) -> dict:
    """Sert le rapport JSON généré par scripts/run_golden_v2.py."""
    import os
    root = os.getcwd()
    report_path = os.path.join(root, "golden", "latest_quality_report.json")

    if not os.path.exists(report_path):
        return {
            "status": "no_report",
            "message": "Aucun rapport généré.",
            "metrics": {"pass_rate": 0, "total": 0, "passed": 0, "failed": 0}
        }

    try:
        with open(report_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.error("golden_report_read_failed", error=str(exc))
        return {"status": "error", "message": str(exc)}


@router.get(
    "/dashboard",
    status_code=status.HTTP_200_OK,
    summary="Statistiques dashboard utilisateur",
)
@router.get(
    "/stats/dashboard",
    include_in_schema=False,
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
        risk_result = await db.execute(
            select(PseudonymMapping.risk_level, func.count())
            .join(Document, PseudonymMapping.document_id == Document.id)
            .where(
                Document.uploaded_by_user_id == user_id,
                Document.is_deleted.is_(False),
            )
            .group_by(PseudonymMapping.risk_level)
        )
        for row in risk_result.all():
            level = row[0] or "low"
            if level in risk_distribution:
                risk_distribution[level] = row[1]
    except Exception:
        pass

    entity_distribution: dict[str, int] = {}
    try:
        entity_result = await db.execute(
            select(EntityDetection.entity_type, func.count())
            .join(Document, EntityDetection.document_id == Document.id)
            .where(
                Document.uploaded_by_user_id == user_id,
                Document.is_deleted.is_(False),
            )
            .group_by(EntityDetection.entity_type)
        )
        entity_distribution = {
            str(row[0] or "unknown").upper(): int(row[1] or 0)
            for row in entity_result.all()
        }
    except Exception:
        entity_distribution = {}

    recent_activity: list[dict] = []
    try:
        from app.models.audit_log import AuditLog
        now = datetime.now(UTC)
        since = now - timedelta(days=6)
        activity_result = await db.execute(
            select(AuditLog.created_at)
            .where(AuditLog.user_id == user_id, AuditLog.created_at >= since)
            .order_by(AuditLog.created_at)
        )
        recent_activity = _created_last_7_days(list(activity_result.scalars().all()), now)
    except Exception:
        pass

    trash_result = await db.execute(
        select(func.count()).select_from(Document).where(
            Document.uploaded_by_user_id == user_id,
            Document.is_deleted.is_(True),
        )
    )
    trashed = trash_result.scalar() or 0

    gdpr_score = _calculate_gdpr_score(
        total_docs,
        status_counts,
        risk_distribution,
        recent_activity,
    )
    ready_docs = status_counts.get("ready", 0) + status_counts.get("anonymized", 0)
    high_or_critical = risk_distribution.get("high", 0) + risk_distribution.get("critical", 0)
    trust_score = compute_portfolio_trust_score(
        total_documents=total_docs,
        gdpr_score=gdpr_score.get("score"),
        ready_documents=ready_docs,
        failed_documents=status_counts.get("failed", 0),
        high_or_critical_risks=high_or_critical,
    )

    return {
        "total_documents": total_docs,
        "total_entities_masked": sum(entity_distribution.values()),
        "status_counts": status_counts,
        "risk_distribution": risk_distribution,
        "entity_distribution": entity_distribution,
        "recent_activity": recent_activity,
        "trashed_documents": trashed,
        "gdpr_score": gdpr_score,
        "trust_score": trust_score,
    }


@router.get(
    "/dossier-360",
    status_code=status.HTTP_200_OK,
    summary="Vue Dossier 360",
)
@router.get(
    "/stats/dossier-360",
    include_in_schema=False,
)
async def get_dossier_360_stats(
    current_user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=6, ge=1, le=20),
) -> dict:
    # On délègue à la fonction de chargement existante
    from app.api.v1._doc_stats import _load_dossier_360_payload
    return await _load_dossier_360_payload(current_user, db, limit)


@router.get(
    "/stats/dossier-360/report",
    status_code=status.HTTP_200_OK,
    summary="Rapport PDF Dossier 360",
)
async def get_dossier_360_report(
    current_user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=20, ge=1, le=50),
) -> Response:
    payload = await _load_dossier_360_payload(current_user, db, limit)

    from app.services.pdf_dossier_360_report_service import generate_dossier_360_pdf

    pdf = generate_dossier_360_pdf(payload)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="dossier-360.pdf"'},
    )


@router.get(
    "/quality-dashboard",
    response_model=QualityDashboardResponse,
    status_code=status.HTTP_200_OK,
    summary="Tableau de bord qualité / business (Data Flywheel)",
)
async def get_quality_dashboard(
    current_user: CurrentUser,
    db: DbSession,
) -> QualityDashboardResponse:
    """Org-scoped quality + business metrics (volume, time-to-value, drafts).

    Filtre strictement sur ``current_user.org_id``. Aucun agrégat cross-org.
    """
    org_id = getattr(current_user, "org_id", None)
    metrics = await compute_quality_metrics(db, org_id)
    return QualityDashboardResponse(
        org_id=metrics.org_id,
        as_of=metrics.as_of,
        total_documents=metrics.total_documents,
        processed_documents=metrics.processed_documents,
        validated_documents=metrics.validated_documents,
        avg_processing_seconds=metrics.avg_processing_seconds,
        avg_time_to_validation_seconds=metrics.avg_time_to_validation_seconds,
        one_shot_full_ready_rate=metrics.one_shot_full_ready_rate,
        avg_human_overrides_per_document=metrics.avg_human_overrides_per_document,
        ai_readiness_score=metrics.ai_readiness_score,
        ai_readiness_level=metrics.ai_readiness_level,
        total_golden_case_drafts=metrics.total_golden_case_drafts,
        accepted_golden_case_drafts=metrics.accepted_golden_case_drafts,
        corrections_by_field=metrics.corrections_by_field,
        corrections_by_error_type=metrics.corrections_by_error_type,
        documents_by_status=metrics.documents_by_status,
    )


@router.get(
    "/status-summary",
    status_code=status.HTTP_200_OK,
    summary="Résumé des statuts",
)
async def get_documents_status_summary(
    current_user: CurrentUser,
    db: DbSession,
    days: int = Query(default=30, ge=1, le=365),
) -> dict:
    user_id = current_user.id
    now = datetime.now(UTC)
    since = now - timedelta(days=days)

    period_result = await db.execute(
        select(Document.status, func.count())
        .where(
            Document.uploaded_by_user_id == user_id,
            Document.is_deleted.is_(False),
            Document.created_at >= since,
        )
        .group_by(Document.status)
    )
    period_status_counts: dict[str, int] = {}
    for row in period_result.all():
        key = _status_key(row[0])
        period_status_counts[key] = row[1]

    current_result = await db.execute(
        select(Document.status, func.count())
        .where(
            Document.uploaded_by_user_id == user_id,
            Document.is_deleted.is_(False),
        )
        .group_by(Document.status)
    )
    current_status_counts: dict[str, int] = {}
    for row in current_result.all():
        key = _status_key(row[0])
        current_status_counts[key] = row[1]

    created_24h_result = await db.execute(
        select(func.count())
        .select_from(Document)
        .where(
            Document.uploaded_by_user_id == user_id,
            Document.is_deleted.is_(False),
            Document.created_at >= now - timedelta(hours=24),
        )
    )
    recent_uploads_24h = int(created_24h_result.scalar() or 0)

    created_7d_result = await db.execute(
        select(Document.created_at).where(
            Document.uploaded_by_user_id == user_id,
            Document.is_deleted.is_(False),
            Document.created_at >= now - timedelta(days=6),
        )
    )
    created_last_7_days = _created_last_7_days(
        list(created_7d_result.scalars().all()),
        now,
    )

    processing_count = (
        current_status_counts.get("processing", 0)
        + current_status_counts.get("extracting", 0)
        + current_status_counts.get("extracted", 0)
        + current_status_counts.get("anonymizing", 0)
    )

    return {
        "period_days": days,
        "status_counts": period_status_counts,
        "current_status_counts": current_status_counts,
        "period_total": sum(period_status_counts.values()),
        "total": sum(current_status_counts.values()),
        "ready": current_status_counts.get("ready", 0),
        "anonymized": current_status_counts.get("anonymized", 0),
        "processing": processing_count,
        "uploaded": current_status_counts.get("uploaded", 0),
        "failed": current_status_counts.get("failed", 0),
        "recent_uploads_24h": recent_uploads_24h,
        "created_last_7_days": created_last_7_days,
        "last_updated": now.isoformat(),
    }


async def _load_dossier_360_payload(current_user, db, limit):
    result = await db.execute(
        select(Document)
        .where(Document.uploaded_by_user_id == current_user.id, Document.is_deleted.is_(False))
        .order_by(desc(Document.updated_at))
        .limit(50)
    )
    docs = result.scalars().all()
    doc_ids = [doc.id for doc in docs]

    risk_by_document: dict[str, float] = {}
    entity_counts_by_document: dict[str, int] = {}
    if doc_ids:
        risk_result = await db.execute(
            select(
                PseudonymMapping.document_id,
                PseudonymMapping.risk_score,
                PseudonymMapping.risk_level,
            ).where(PseudonymMapping.document_id.in_(doc_ids))
        )
        fallback_by_level = {"low": 10.0, "medium": 45.0, "high": 70.0, "critical": 90.0}
        for document_id, risk_score, risk_level in risk_result.all():
            normalized_score = _risk_score_percent(risk_score)
            if not normalized_score:
                normalized_score = fallback_by_level.get(str(risk_level or "low").lower(), 0.0)
            key = str(document_id)
            risk_by_document[key] = max(risk_by_document.get(key, 0.0), normalized_score)

        entity_result = await db.execute(
            select(EntityDetection.document_id, func.count())
            .where(EntityDetection.document_id.in_(doc_ids))
            .group_by(EntityDetection.document_id)
        )
        entity_counts_by_document = {
            str(document_id): int(count or 0)
            for document_id, count in entity_result.all()
        }

    return build_dossier_360(
        [_document_to_dossier_360_input(document) for document in docs],
        risk_by_document=risk_by_document,
        entity_counts_by_document=entity_counts_by_document,
        limit=limit,
    )
