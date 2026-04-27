"""ConfiDoc Backend — Clients Endpoints."""

from __future__ import annotations

import uuid
from fastapi import APIRouter, status, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import http_404
from app.core.logging import get_logger
from app.models.client import Client
from app.schemas.client import ClientCreate, ClientResponse, ClientUpdate

router = APIRouter()
logger = get_logger(__name__)


@router.get(
    "/",
    response_model=list[ClientResponse],
    status_code=status.HTTP_200_OK,
    summary="Liste des clients de l'organisation",
)
async def list_clients(
    current_user: CurrentUser,
    db: DbSession,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[Client]:
    """Retourne la liste des clients pour l'organisation de l'utilisateur."""
    result = await db.execute(
        select(Client)
        .where(
            Client.org_id == current_user.org_id,
            Client.is_deleted.is_(False)
        )
        .order_by(Client.name)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


@router.post(
    "/",
    response_model=ClientResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un nouveau client",
)
async def create_client(
    client_in: ClientCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> Client:
    """Crée un nouveau client rattaché à l'organisation."""
    client = Client(
        **client_in.model_dump(),
        org_id=current_user.org_id
    )
    db.add(client)
    await db.commit()
    await db.refresh(client)
    logger.info("client_created", client_id=str(client.id), user_id=str(current_user.id))
    return client


@router.get(
    "/{client_id}",
    response_model=ClientResponse,
    status_code=status.HTTP_200_OK,
    summary="Détails d'un client",
)
async def get_client(
    client_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> Client:
    """Récupère un client par son ID."""
    result = await db.execute(
        select(Client).where(
            Client.id == client_id,
            Client.org_id == current_user.org_id,
            Client.is_deleted.is_(False)
        )
    )
    client = result.scalar_one_or_none()
    if not client:
        raise http_404("Client non trouvé")
    return client


@router.patch(
    "/{client_id}",
    response_model=ClientResponse,
    status_code=status.HTTP_200_OK,
    summary="Modifier un client",
)
async def update_client(
    client_id: uuid.UUID,
    client_in: ClientUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> Client:
    """Met à jour les informations d'un client."""
    result = await db.execute(
        select(Client).where(
            Client.id == client_id,
            Client.org_id == current_user.org_id,
            Client.is_deleted.is_(False)
        )
    )
    client = result.scalar_one_or_none()
    if not client:
        raise http_404("Client non trouvé")
    
    update_data = client_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(client, field, value)
    
    await db.commit()
    await db.refresh(client)
    logger.info("client_updated", client_id=str(client.id), user_id=str(current_user.id))
    return client


@router.delete(
    "/{client_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer un client",
)
async def delete_client(
    client_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """Supprime (soft delete) un client."""
    result = await db.execute(
        select(Client).where(
            Client.id == client_id,
            Client.org_id == current_user.org_id,
            Client.is_deleted.is_(False)
        )
    )
    client = result.scalar_one_or_none()
    if not client:
        raise http_404("Client non trouvé")
    
    client.is_deleted = True
    from datetime import datetime, UTC
    client.deleted_at = datetime.now(UTC)
    
    await db.commit()
    logger.info("client_deleted", client_id=str(client_id), user_id=str(current_user.id))
