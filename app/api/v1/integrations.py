"""API-first integration endpoints for cabinets."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Request, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import http_400, http_403, http_404
from app.core.rls import commit_and_restore_rls_context, set_rls_context
from app.core.security import generate_opaque_token, hash_token
from app.models.integration import ApiKey, WebhookEndpoint
from app.models.membership import Membership
from app.models.organization import Organization, PlanType, ProfessionType
from app.models.role import Role
from app.schemas.integration import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyResponse,
    IntegrationGuideResponse,
    WebhookCreateRequest,
    WebhookCreateResponse,
    WebhookResponse,
    WebhookTestResponse,
)
from app.services.integration_service import (
    api_key_prefix,
    generate_api_key_value,
    public_app_base_url,
)
from app.services.webhook_notify import notify_json_webhook

router = APIRouter()


async def _current_org_id(request: Request, current_user: CurrentUser, db: DbSession) -> UUID:
    org_id = getattr(request.state, "org_id", None)
    if org_id:
        return org_id

    if not current_user.is_platform_admin:
        raise http_400("Organisation introuvable pour cet utilisateur")

    result = await db.execute(select(Organization).where(Organization.slug == "confidoc-admin"))
    organization = result.scalar_one_or_none()
    if not organization:
        organization = Organization(
            name="ConfiDoc Admin",
            slug="confidoc-admin",
            profession_type=ProfessionType.CABINET_COMPTABLE,
            plan=PlanType.ENTERPRISE,
            is_active=True,
        )
        db.add(organization)
        await db.flush()

    result = await db.execute(
        select(Role).where(Role.org_id == organization.id, Role.name == "owner")
    )
    role = result.scalar_one_or_none()
    if not role:
        role = Role(
            org_id=organization.id,
            name="owner",
            permissions=["*"],
            is_system=True,
        )
        db.add(role)
        await db.flush()

    result = await db.execute(
        select(Membership).where(
            Membership.user_id == current_user.id,
            Membership.org_id == organization.id,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        membership = Membership(
            user_id=current_user.id,
            org_id=organization.id,
            role_id=role.id,
            is_active=True,
        )
        db.add(membership)
    elif not membership.is_active:
        membership.is_active = True

    await db.commit()
    request.state.org_id = organization.id
    request.state.membership = membership
    current_user.org_id = organization.id
    await set_rls_context(db, org_id=organization.id, user_id=current_user.id)
    return organization.id


def _require_human_session(request: Request) -> None:
    if getattr(request.state, "auth_type", "") == "api_key":
        raise http_403("Gestion des integrations reservee a une session utilisateur")


def _api_key_response(api_key: ApiKey) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        scopes=api_key.scopes or [],
        is_active=api_key.is_active,
        last_used_at=api_key.last_used_at,
        expires_at=api_key.expires_at,
        revoked_at=api_key.revoked_at,
        created_at=api_key.created_at,
    )


def _webhook_response(endpoint: WebhookEndpoint) -> WebhookResponse:
    return WebhookResponse(
        id=endpoint.id,
        name=endpoint.name,
        url=endpoint.url,
        events=endpoint.events or [],
        is_active=endpoint.is_active,
        failure_count=endpoint.failure_count,
        last_success_at=endpoint.last_success_at,
        last_failure_at=endpoint.last_failure_at,
        created_at=endpoint.created_at,
    )


@router.post(
    "/api-keys",
    response_model=ApiKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Creer une cle API cabinet",
)
async def create_api_key(
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
    payload: ApiKeyCreateRequest,
) -> ApiKeyCreateResponse:
    _require_human_session(request)
    org_id = await _current_org_id(request, current_user, db)
    raw_key = generate_api_key_value()
    api_key = ApiKey(
        org_id=org_id,
        created_by_user_id=current_user.id,
        name=payload.name.strip(),
        key_prefix=api_key_prefix(raw_key),
        key_hash=hash_token(raw_key),
        scopes=payload.scopes,
        expires_at=payload.expires_at,
    )
    db.add(api_key)
    await commit_and_restore_rls_context(db, org_id=org_id, user_id=current_user.id)
    await db.refresh(api_key)
    return ApiKeyCreateResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        api_key=raw_key,
        scopes=api_key.scopes or [],
        expires_at=api_key.expires_at,
        created_at=api_key.created_at,
    )


@router.get(
    "/api-keys",
    response_model=list[ApiKeyResponse],
    status_code=status.HTTP_200_OK,
    summary="Lister les cles API du cabinet",
)
async def list_api_keys(
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> list[ApiKeyResponse]:
    _require_human_session(request)
    org_id = await _current_org_id(request, current_user, db)
    result = await db.execute(
        select(ApiKey).where(ApiKey.org_id == org_id).order_by(ApiKey.created_at.desc())
    )
    return [_api_key_response(api_key) for api_key in result.scalars().all()]


@router.delete(
    "/api-keys/{api_key_id}",
    status_code=status.HTTP_200_OK,
    summary="Revoquer une cle API",
)
async def revoke_api_key(
    api_key_id: UUID,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    _require_human_session(request)
    org_id = await _current_org_id(request, current_user, db)
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == api_key_id, ApiKey.org_id == org_id)
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise http_404("Cle API introuvable")
    api_key.is_active = False
    api_key.revoked_at = datetime.now(UTC)
    await db.commit()
    return {"status": "revoked", "id": str(api_key.id)}


@router.post(
    "/webhooks",
    response_model=WebhookCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Creer un webhook cabinet",
)
async def create_webhook(
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
    payload: WebhookCreateRequest,
) -> WebhookCreateResponse:
    _require_human_session(request)
    org_id = await _current_org_id(request, current_user, db)
    secret = payload.signing_secret or generate_opaque_token(32)
    endpoint = WebhookEndpoint(
        org_id=org_id,
        created_by_user_id=current_user.id,
        name=payload.name.strip(),
        url=str(payload.url),
        signing_secret=secret,
        events=payload.events,
    )
    db.add(endpoint)
    await commit_and_restore_rls_context(db, org_id=org_id, user_id=current_user.id)
    await db.refresh(endpoint)
    base = _webhook_response(endpoint).model_dump()
    return WebhookCreateResponse(**base, signing_secret=secret)


@router.get(
    "/webhooks",
    response_model=list[WebhookResponse],
    status_code=status.HTTP_200_OK,
    summary="Lister les webhooks du cabinet",
)
async def list_webhooks(
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> list[WebhookResponse]:
    _require_human_session(request)
    org_id = await _current_org_id(request, current_user, db)
    result = await db.execute(
        select(WebhookEndpoint)
        .where(WebhookEndpoint.org_id == org_id)
        .order_by(WebhookEndpoint.created_at.desc())
    )
    return [_webhook_response(endpoint) for endpoint in result.scalars().all()]


@router.delete(
    "/webhooks/{webhook_id}",
    status_code=status.HTTP_200_OK,
    summary="Desactiver un webhook",
)
async def deactivate_webhook(
    webhook_id: UUID,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    _require_human_session(request)
    org_id = await _current_org_id(request, current_user, db)
    result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.id == webhook_id,
            WebhookEndpoint.org_id == org_id,
        )
    )
    endpoint = result.scalar_one_or_none()
    if not endpoint:
        raise http_404("Webhook introuvable")
    endpoint.is_active = False
    await db.commit()
    return {"status": "disabled", "id": str(endpoint.id)}


@router.post(
    "/webhooks/{webhook_id}/test",
    response_model=WebhookTestResponse,
    status_code=status.HTTP_200_OK,
    summary="Envoyer un evenement de test",
)
async def test_webhook(
    webhook_id: UUID,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> WebhookTestResponse:
    _require_human_session(request)
    org_id = await _current_org_id(request, current_user, db)
    result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.id == webhook_id,
            WebhookEndpoint.org_id == org_id,
            WebhookEndpoint.is_active.is_(True),
        )
    )
    endpoint = result.scalar_one_or_none()
    if not endpoint:
        raise http_404("Webhook actif introuvable")
    delivered, status_code, error, _attempts, _preview = await notify_json_webhook(
        event="integration.test",
        payload={
            "event": "integration.test",
            "event_id": generate_opaque_token(18),
            "created_at": datetime.now(UTC).isoformat(),
            "message": "ConfiDoc webhook test",
        },
        url=endpoint.url,
        secret=endpoint.signing_secret,
    )
    now = datetime.now(UTC)
    if delivered:
        endpoint.last_success_at = now
        endpoint.failure_count = 0
    else:
        endpoint.last_failure_at = now
        endpoint.failure_count = (endpoint.failure_count or 0) + 1
    await db.commit()
    if not delivered:
        return WebhookTestResponse(
            status=f"failed:{status_code or error or 'unknown'}",
            endpoint_id=endpoint.id,
            delivered=False,
        )
    return WebhookTestResponse(status="delivered", endpoint_id=endpoint.id, delivered=True)


@router.get(
    "/guide",
    response_model=IntegrationGuideResponse,
    status_code=status.HTTP_200_OK,
    summary="Guide rapide API cabinet",
)
async def integration_guide(request: Request) -> IntegrationGuideResponse:
    base_url = public_app_base_url(str(request.base_url)) + "/api/v1"
    return IntegrationGuideResponse(
        title="ConfiDoc Cabinet API",
        base_url=base_url,
        auth_header="Authorization: Bearer confidoc_live_...",
        upload_example={
            "method": "POST",
            "url": f"{base_url}/uploads",
            "query": {
                "auto_anonymize": True,
                "profile": "dataset_accounting_pseudo",
                "document_type": "accounting",
                "client_name": "WEMADE",
            },
            "headers": {
                "Authorization": "Bearer confidoc_live_...",
                "Idempotency-Key": "wemade-2024-liasse-v1",
            },
            "multipart": {"file": "@plaquette.pdf"},
        },
        webhook_events=["document.ready", "document.failed", "document.validated"],
    )
