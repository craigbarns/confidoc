"""ConfiDoc Backend — Auth Service."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import http_400, http_401
from app.core.security import (
    create_access_token,
    generate_opaque_token,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse

settings = get_settings()


async def authenticate_user(
    db: AsyncSession, login_req: LoginRequest
) -> TokenResponse:
    """Verifie le compte et génère la paire JWT + Refresh."""
    normalized_email = str(login_req.email).strip().lower()
    stmt = select(User).where(User.email == normalized_email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise http_401("Email ou mot de passe incorrect")

    if not verify_password(login_req.password, user.password_hash):
        raise http_401("Email ou mot de passe incorrect")

    if not user.is_active:
        raise http_400("Ce compte est désactivé")

    # Mettre à jour last_login
    user.last_login_at = datetime.now(timezone.utc)
    
    # Générer le token d'accès
    access_token = create_access_token(user.id)

    # Générer le refresh token (stocké en base)
    refresh_token_value = generate_opaque_token()
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )

    new_refresh = RefreshToken(
        user_id=user.id,
        token=refresh_token_value,
        expires_at=expires_at,
    )
    db.add(new_refresh)

    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token_value,
    )


async def refresh_access_token(
    db: AsyncSession, refresh_token_value: str
) -> TokenResponse:
    """Consomme le refresh token et en génère un nouveau + JWT."""
    stmt = select(RefreshToken).where(RefreshToken.token == refresh_token_value)
    result = await db.execute(stmt)
    rt = result.scalar_one_or_none()

    if not rt:
        raise http_401("Refresh token invalide ou introuvable")

    if rt.is_revoked:
        # Faille de sécurité : un token révoqué est réutilisé !
        # On peut révoquer tous les tokens de cet utilisateur ici
        stmt_revoke_all = delete(RefreshToken).where(RefreshToken.user_id == rt.user_id)
        await db.execute(stmt_revoke_all)
        await db.commit()
        raise http_401("Ce token a été révoqué, session terminée")

    if rt.expires_at < datetime.now(timezone.utc):
        raise http_401("Refresh token expiré")

    # Rotation de token : on supprime l'ancien
    await db.delete(rt)

    # Récupérer user
    stmt_user = select(User).where(User.id == rt.user_id)
    user_res = await db.execute(stmt_user)
    user = user_res.scalar_one()

    if not user.is_active:
        raise http_401("Compte utilisateur désactivé")

    # Génération
    new_access = create_access_token(user.id)
    new_refresh_value = generate_opaque_token()
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )

    new_rt = RefreshToken(
        user_id=user.id,
        token=new_refresh_value,
        expires_at=expires_at,
    )
    db.add(new_rt)

    await db.commit()

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh_value,
    )


async def logout_user(db: AsyncSession, user_id: str) -> None:
    """Déconnexion : révoque tous les refresh tokens de l'utilisateur."""
    stmt = delete(RefreshToken).where(RefreshToken.user_id == user_id)
    await db.execute(stmt)
    await db.commit()
