"""ConfiDoc Backend — Auth Endpoints."""

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.core.logging import get_logger
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse
from app.services import auth_service

router = APIRouter()
logger = get_logger(__name__)


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
    await auth_service.logout_user(db, current_user.id)
    logger.info("auth_logout", user_id=str(current_user.id))
