"""ConfiDoc Backend — Auth Endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.config import get_settings
from app.core.exceptions import http_400
from app.core.logging import get_logger
from app.core.security import get_password_hash
from app.models.user import User
from app.schemas.auth import (
    BootstrapAdminRequest,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
)
from app.services import auth_service

router = APIRouter()
logger = get_logger(__name__)
settings = get_settings()


class RecoveryResetRequest(BaseModel):
    email: EmailStr
    new_password: str
    recovery_token: str


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authentification (Email/Mot de passe)",
)
async def login(
    login_req: LoginRequest,
    db: DbSession,
) -> TokenResponse:
    """Authentifie un utilisateur et retourne la paire de tokens."""
    logger.info("auth_login_attempt", email=login_req.email)
    return await auth_service.authenticate_user(db, login_req)


@router.post(
    "/token",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authentification OAuth2 Formulaire (Swagger UI)",
    include_in_schema=False,
)
async def login_form_oauth2(
    db: DbSession,
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> TokenResponse:
    """Endpoint utilisé par le Swagger UI pour l'accès Bearer Auth."""
    req = LoginRequest(email=form_data.username, password=form_data.password)
    return await auth_service.authenticate_user(db, req)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Rafraîchir le token d'accès",
)
async def refresh_token(
    refresh_req: RefreshRequest,
    db: DbSession,
) -> TokenResponse:
    """Consomme le refresh token pour recréer JWT + nouveau Refresh."""
    return await auth_service.refresh_access_token(db, refresh_req.refresh_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Déconnexion totale de l'utilisateur",
)
async def logout(
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """Déconnecte l'utilisateur en révoquant ses refresh tokens."""
    await auth_service.logout_user(db, str(current_user.id))
    logger.info("auth_logout", user_id=str(current_user.id))


@router.post(
    "/bootstrap-admin",
    status_code=status.HTTP_201_CREATED,
    summary="Créer le premier admin plateforme",
)
async def bootstrap_admin(
    payload: BootstrapAdminRequest,
    db: DbSession,
) -> dict[str, str]:
    """Crée le premier admin si aucun admin plateforme n'existe."""
    existing_admin = await db.execute(
        select(User).where(User.is_platform_admin.is_(True))
    )
    if existing_admin.scalar_one_or_none():
        raise http_400("Un admin plateforme existe déjà")

    existing_email = await db.execute(select(User).where(User.email == payload.email))
    if existing_email.scalar_one_or_none():
        raise http_400("Cet email existe déjà")

    user = User(
        email=str(payload.email).lower(),
        password_hash=get_password_hash(payload.password),
        first_name=payload.first_name.strip() or "Super",
        last_name=payload.last_name.strip() or "Admin",
        is_active=True,
        is_platform_admin=True,
    )
    db.add(user)
    await db.commit()

    logger.info("bootstrap_admin_created", email=user.email)
    return {"status": "created", "email": user.email}


@router.post(
    "/recover-access",
    status_code=status.HTTP_200_OK,
    summary="Réinitialiser un accès via token de récupération",
)
async def recover_access(
    payload: RecoveryResetRequest,
    db: DbSession,
) -> dict[str, str]:
    """Recovery d'urgence en production, protégé par token Railway.

    Désactivé tant que ADMIN_RECOVERY_TOKEN n'est pas configuré.
    """
    recovery_token = (getattr(settings, "ADMIN_RECOVERY_TOKEN", "") or "").strip()
    if not recovery_token:
        raise http_400("Recovery désactivé: configurez ADMIN_RECOVERY_TOKEN")
    if payload.recovery_token.strip() != recovery_token:
        raise http_400("Recovery token invalide")
    if len(payload.new_password or "") < 8:
        raise http_400("Le nouveau mot de passe doit contenir au moins 8 caractères")

    user_res = await db.execute(
        select(User).where(User.email == str(payload.email).strip().lower())
    )
    user = user_res.scalar_one_or_none()
    if not user:
        raise http_400("Utilisateur introuvable")

    user.password_hash = get_password_hash(payload.new_password)
    user.is_active = True
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    logger.warning("auth_recovery_password_reset", email=user.email)
    return {"status": "password_reset", "email": user.email}
