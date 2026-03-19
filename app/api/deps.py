"""ConfiDoc Backend — Dépendances API (Dependency Injection)."""

from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import http_401, http_403
from app.core.security import decode_access_token
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/token",
    auto_error=False,
)

# Raccourci de typing utile pour les endpoints
DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    request: Request,
    db: DbSession,
    token: str | None = Depends(oauth2_scheme),
) -> User:
    """Dépendance : récupère l'utilisateur connecté via le Bearer Token.

    Lease et stocke le user dans `request.state.user` pour accès ultérieur,
    ainsi que l'org_id courant.
    """
    if not token:
        # Fallback pour le JWT complet passé en header Authorization "Bearer ..."
        # oauth2_scheme gère ça normalement, mais si pas de token :
        raise http_401("Authentification requise")

    payload = decode_access_token(token)
    if not payload:
        raise http_401("Token invalide ou expiré")

    user_id_str: str | Any = payload.get("sub")
    if not user_id_str:
        raise http_401("Payload invalide")

    # Fetch user depuis BDD
    stmt = select(User).where(User.id == user_id_str)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise http_401("Utilisateur introuvable")

    if not user.is_active:
        raise http_403("Compte désactivé")

    # Stocker en request state pour les hooks RBAC plus tard
    request.state.user = user

    return user


async def require_platform_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dépendance : exige un compte superadmin plateforme."""
    if not current_user.is_platform_admin:
        raise http_403("Accès réservé aux administrateurs de la plateforme")
    return current_user


CurrentUser = Annotated[User, Depends(get_current_user)]
PlatformAdmin = Annotated[User, Depends(require_platform_admin)]
