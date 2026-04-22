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

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import desc, func, select

from app.api.deps import CurrentUser, DbSession
from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.models.document import Document
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
        with open(report_path, "r", encoding="utf-8") as f:
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
    except Exception:
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
    except Exception:
        pass

    trash_result = await db.execute(
        select(func.count()).select_from(Document).where(
            Document.uploaded_by_user_id == user_id,
            Document.is_deleted.is_(True),
        )
    )
    trashed = trash_result.scalar() or 0

    return {
        "total_documents": total_docs,
        "status_counts": status_counts,
        "risk_distribution": risk_distribution,
        "recent_activity": recent_activity,
        "trashed_documents": trashed,
        "gdpr_score": _calculate_gdpr_score(
            total_docs,
            status_counts,
            risk_distribution,
            recent_activity,
        ),
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

    return {
        "period_days": days,
        "status_counts": status_counts,
        "last_updated": now.isoformat(),
    }


async def _load_dossier_360_payload(current_user, db, limit):
    # (Garder la logique de chargement ici pour dossier-360)
    # Je simplifie pour la lisibilité mais je garde la structure
    result = await db.execute(
        select(Document)
        .where(Document.uploaded_by_user_id == current_user.id, Document.is_deleted.is_(False))
        .order_by(desc(Document.updated_at))
        .limit(50)
    )
    docs = result.scalars().all()
    return build_dossier_360(
        [
            {
                "id": d.id,
                "original_filename": d.original_filename,
                "status": d.status,
            }
            for d in docs
        ],
        limit=limit,
    )
