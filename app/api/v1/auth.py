"""ConfiDoc Backend — Auth Endpoints."""

import re
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select

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

# ── Redis-backed rate limiter for login ───────────────────────────────
# Uses Redis INCR + EXPIRE so it survives restarts and multi-instance deploys.
# Falls back to in-memory if Redis is unavailable (dev mode).

_RATE_WINDOW = 300  # 5 minutes sliding window
_RATE_MAX = 10  # max attempts per window

# In-memory fallback (single-process, dev only)
_login_attempts_fallback: dict[str, list[float]] = {}


async def _check_rate_limit(key: str) -> None:
    """Raise 429 if too many login attempts within the sliding window."""
    import time

    redis_key = f"confidoc:auth_rl:{key}"
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=1)
        async with r:
            pipe = r.pipeline()
            pipe.incr(redis_key)
            pipe.expire(redis_key, _RATE_WINDOW)
            results = await pipe.execute()
            count = int(results[0])
        if count > _RATE_MAX:
            logger.warning("auth_rate_limited_redis", key=key, count=count)
            raise HTTPException(
                status_code=429,
                detail="Trop de tentatives. Réessayez dans quelques minutes.",
            )
    except HTTPException:
        raise
    except Exception as redis_err:
        # Redis indisponible → fallback in-memory (dev/test uniquement)
        logger.debug("auth_rate_limit_redis_unavailable", error=str(redis_err))
        now = time.time()
        attempts = _login_attempts_fallback.get(key, [])
        attempts = [t for t in attempts if now - t < _RATE_WINDOW]
        if len(attempts) >= _RATE_MAX:
            logger.warning("auth_rate_limited_fallback", key=key, attempts=len(attempts))
            raise HTTPException(
                status_code=429,
                detail="Trop de tentatives. Réessayez dans quelques minutes.",
            ) from None
        attempts.append(now)
        _login_attempts_fallback[key] = attempts


_PASSWORD_MIN_LENGTH = 8
_PASSWORD_PATTERN = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$")


def _validate_password(v: str) -> str:
    if len(v) < _PASSWORD_MIN_LENGTH:
        raise ValueError("Le mot de passe doit contenir au moins 8 caractères")
    if not _PASSWORD_PATTERN.match(v):
        raise ValueError(
            "Le mot de passe doit contenir au moins une majuscule, une minuscule et un chiffre"
        )
    return v


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        return _validate_password(v)


class RecoveryResetRequest(BaseModel):
    email: EmailStr
    new_password: str
    recovery_token: str

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        return _validate_password(v)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authentification (Email/Mot de passe)",
)
async def login(
    login_req: LoginRequest,
    db: DbSession,
    request: Request,
) -> TokenResponse:
    """Authentifie un utilisateur et retourne la paire de tokens."""
    client_ip = request.client.host if request.client else "unknown"
    await _check_rate_limit(f"login:{client_ip}")
    logger.info("auth_login_attempt", email=login_req.email, client_ip=client_ip)
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
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),  # noqa: B008
) -> TokenResponse:
    """Endpoint utilisé par le Swagger UI pour l'accès Bearer Auth."""
    client_ip = request.client.host if request.client else "unknown"
    await _check_rate_limit(f"login:{client_ip}")
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
) -> Response:
    """Déconnecte l'utilisateur en révoquant ses refresh tokens."""
    await auth_service.logout_user(db, str(current_user.id))
    logger.info("auth_logout", user_id=str(current_user.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/bootstrap-admin",
    status_code=status.HTTP_201_CREATED,
    summary="Créer le premier admin plateforme",
)
async def bootstrap_admin(
    payload: BootstrapAdminRequest,
    db: DbSession,
) -> dict[str, str]:
    """Crée le premier admin si aucun admin plateforme n'existe.

    En production, requiert que BOOTSTRAP_SECRET soit configuré et fourni
    dans le header X-Bootstrap-Secret pour éviter un takeover sur déploiement vierge.
    """
    # ── Guard production ──────────────────────────────────────────────
    if settings.is_production:
        bootstrap_secret = (getattr(settings, "BOOTSTRAP_SECRET", "") or "").strip()
        if not bootstrap_secret:
            raise http_400("bootstrap-admin désactivé en production : configurez BOOTSTRAP_SECRET.")
        provided = (
            payload.bootstrap_secret if hasattr(payload, "bootstrap_secret") else ""
        ).strip()
        if not secrets.compare_digest(provided, bootstrap_secret):
            logger.warning("bootstrap_admin_unauthorized_attempt")
            raise HTTPException(status_code=403, detail="Accès refusé.")

    existing_admin = await db.execute(select(User).where(User.is_platform_admin.is_(True)))
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
    "/forgot-password",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Demande de réinitialisation de mot de passe",
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: DbSession,
    request: Request,
) -> dict[str, str]:
    """Envoie un email de reset si le compte existe.

    Toujours 202 pour éviter l'énumération d'adresses email.
    """
    client_ip = request.client.host if request.client else "unknown"
    await _check_rate_limit(f"forgot:{client_ip}")
    await auth_service.request_password_reset(db, str(payload.email))
    return {"detail": "Si ce compte existe, un email de réinitialisation a été envoyé."}


@router.post(
    "/reset-password",
    status_code=status.HTTP_200_OK,
    summary="Réinitialiser le mot de passe avec le token reçu par email",
)
async def reset_password(
    payload: ResetPasswordRequest,
    db: DbSession,
) -> dict[str, str]:
    """Consomme le token de reset et met à jour le mot de passe."""
    await auth_service.reset_password(db, payload.token, payload.new_password)
    return {"detail": "Mot de passe mis à jour. Reconnectez-vous."}


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
    # Timing-safe comparison to prevent timing attacks
    if not secrets.compare_digest(payload.recovery_token.strip(), recovery_token):
        logger.warning("auth_recovery_invalid_token", email=str(payload.email))
        raise http_400("Recovery token invalide")

    user_res = await db.execute(
        select(User).where(User.email == str(payload.email).strip().lower())
    )
    user = user_res.scalar_one_or_none()
    if not user:
        raise http_400("Utilisateur introuvable")

    user.password_hash = get_password_hash(payload.new_password)
    user.is_active = True
    user.last_login_at = datetime.now(UTC)
    await db.commit()
    logger.warning("auth_recovery_password_reset", email=user.email)
    return {"status": "password_reset", "email": user.email}
