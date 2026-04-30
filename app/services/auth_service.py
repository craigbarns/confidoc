"""ConfiDoc Backend — Auth Service."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import http_400, http_401
from app.core.security import (
    create_access_token,
    generate_opaque_token,
    hash_token,
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
        token=hash_token(refresh_token_value),
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
    stmt = select(RefreshToken).where(RefreshToken.token == hash_token(refresh_token_value))
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

    # Rotation : DELETE explicite (évite SAWarning "0 rows matched" en course
    # parallèle / double refresh) + expunge pour ne pas re-émettre un DELETE ORM au flush.
    res = await db.execute(delete(RefreshToken).where(RefreshToken.id == rt.id))
    if res.rowcount == 0:
        await db.rollback()
        raise http_401("Refresh token déjà utilisé")
    await db.run_sync(lambda s: s.expunge(rt))

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
        token=hash_token(new_refresh_value),
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


# ── Password reset ────────────────────────────────────────────────────

async def request_password_reset(db: AsyncSession, email: str) -> None:
    """Génère un token de reset et envoie l'email.

    Ne lève jamais d'exception visible (anti-enumeration : même réponse
    que l'email existe ou non).
    """
    from app.core.security import generate_opaque_token, hash_token
    from app.models.password_reset_token import PasswordResetToken
    from app.services.email_service import send_password_reset_email

    normalized = email.strip().lower()
    result = await db.execute(select(User).where(User.email == normalized))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        return  # silencieux

    # Invalider les anciens tokens pour cet utilisateur
    await db.execute(
        delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
    )

    token_value = generate_opaque_token(40)
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
    )
    db.add(PasswordResetToken(
        user_id=user.id,
        token=hash_token(token_value),
        expires_at=expires_at,
    ))
    await db.commit()

    reset_url = f"{settings.APP_BASE_URL}/ui?reset_token={token_value}"
    await send_password_reset_email(normalized, reset_url)


async def reset_password(db: AsyncSession, token_value: str, new_password: str) -> None:
    """Vérifie le token et met à jour le mot de passe."""
    from app.core.security import hash_token, get_password_hash
    from app.models.password_reset_token import PasswordResetToken

    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token == hash_token(token_value)
        )
    )
    prt = result.scalar_one_or_none()

    if not prt:
        raise http_400("Token invalide ou expiré")

    if prt.expires_at < datetime.now(timezone.utc):
        await db.delete(prt)
        await db.commit()
        raise http_400("Token expiré. Faites une nouvelle demande.")

    user_result = await db.execute(select(User).where(User.id == prt.user_id))
    user = user_result.scalar_one_or_none()

    if not user or not user.is_active:
        raise http_400("Compte introuvable ou désactivé")

    user.password_hash = get_password_hash(new_password)
    user.last_login_at = datetime.now(timezone.utc)

    # Invalider toutes les sessions actives (refresh tokens)
    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user.id))
    # Consommer le reset token
    await db.delete(prt)
    await db.commit()
