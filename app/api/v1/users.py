"""ConfiDoc Backend — Users Endpoints."""

from fastapi import APIRouter, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.core.logging import get_logger
from app.models.user import User
from app.schemas.user import UserResponse

router = APIRouter()
logger = get_logger(__name__)


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Profil courant de l'utilisateur",
)
async def read_users_me(
    current_user: CurrentUser,
) -> UserResponse:
    """Retourne les informations de l'utilisateur connecté."""
    # current_user est injecté par la dépendance API get_current_user
    return current_user
