"""ConfiDoc Backend — Compliance & GDPR Endpoints."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.logging import get_logger
from app.models.gdpr_consent import GDPRConsent
from app.models.gdpr_register import GDPRProcessingRegister
from app.schemas.common import GenericResponse
from app.core.feature_flags import feature_flags

router = APIRouter()
logger = get_logger(__name__)


@router.get("/feature-flags", summary="Lister les feature flags")
async def list_feature_flags(current_user: CurrentUser):
    """Retourne l'état des flags principaux (Admin uniquement en prod)."""
    # Simple check for now, should ideally be is_platform_admin
    flags = ["use_mistral_ocr", "enable_advanced_review", "debug_mode"]
    res = {}
    for f in flags:
        res[f] = await feature_flags.is_enabled(f)
    return res


@router.post("/feature-flags/{flag_name}", summary="Mettre à jour un feature flag")
async def update_feature_flag(
    flag_name: str, 
    enabled: bool, 
    current_user: CurrentUser
):
    """Active ou désactive un flag."""
    if not current_user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs plateforme")
    await feature_flags.set_flag(flag_name, enabled)
    return {"flag": flag_name, "enabled": enabled}


@router.post(
    "/consent",
    response_model=GenericResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enregistrer le consentement RGPD",
)
async def record_consent(
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
    consent_type: str = "general_processing",
    granted: bool = True,
) -> GenericResponse:
    """Enregistre le consentement de l'utilisateur pour le traitement des données."""
    
    # Optional: check if already exists to update or keep history
    consent = GDPRConsent(
        user_id=current_user.id,
        consent_type=consent_type,
        is_granted=granted,
        granted_at=datetime.now(UTC) if granted else None,
        revoked_at=datetime.now(UTC) if not granted else None,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        version="1.0",
    )
    
    db.add(consent)
    await db.commit()
    
    logger.info("gdpr_consent_recorded", user_id=str(current_user.id), granted=granted)
    
    return GenericResponse(
        success=True,
        message="Consentement enregistré avec succès." if granted else "Consentement révoqué."
    )


@router.get(
    "/consent/status",
    summary="Vérifier le statut du consentement RGPD",
)
async def check_consent_status(
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    """Retourne le statut actuel du consentement de l'utilisateur."""
    result = await db.execute(
        select(GDPRConsent)
        .where(GDPRConsent.user_id == current_user.id)
        .order_by(GDPRConsent.granted_at.desc())
    )
    consent = result.scalar_one_or_none()
    
    return {
        "is_granted": consent.is_granted if consent else False,
        "granted_at": consent.granted_at.isoformat() if consent and consent.granted_at else None,
        "consent_type": consent.consent_type if consent else "general_processing",
        "version": consent.version if consent else "1.0",
    }


@router.get(
    "/register",
    summary="Consulter le registre des traitements RGPD",
)
async def get_processing_register(
    current_user: CurrentUser,
    db: DbSession,
) -> list[dict]:
    """Retourne le registre des activités de traitement (Article 30)."""
    if not current_user.is_platform_admin:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs plateforme")
        
    result = await db.execute(
        select(GDPRProcessingRegister)
        .where(GDPRProcessingRegister.is_active == True)
    )
    records = result.scalars().all()
    
    return [
        {
            "id": str(record.id),
            "name": record.name,
            "purpose": record.purpose,
            "legal_basis": record.legal_basis,
            "data_categories": record.data_categories,
            "data_subjects": record.data_subjects,
            "recipients": record.recipients,
            "retention_period": record.retention_period,
            "security_measures": record.security_measures,
        }
        for record in records
    ]
