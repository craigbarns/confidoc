"""ConfiDoc Backend — Dossiers (Exercices) Endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status
from sqlalchemy import desc, select

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import http_400, http_404
from app.core.logging import get_logger
from app.core.rls import commit_and_restore_rls_context
from app.models.client import Client
from app.models.dossier import Dossier
from app.schemas.dossier import DossierCreate, DossierResponse

router = APIRouter()
logger = get_logger(__name__)


@router.get(
    "/",
    response_model=list[DossierResponse],
    status_code=status.HTTP_200_OK,
    summary="Liste des dossiers (exercices)",
)
async def list_dossiers(
    current_user: CurrentUser,
    db: DbSession,
    client_id: uuid.UUID | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[Dossier]:
    """Liste les dossiers, optionnellement filtrés par client."""
    query = select(Dossier).where(
        Dossier.org_id == current_user.org_id, Dossier.is_deleted.is_(False)
    )
    if client_id:
        query = query.where(Dossier.client_id == client_id)

    result = await db.execute(query.order_by(desc(Dossier.exercice)).offset(skip).limit(limit))
    return list(result.scalars().all())


@router.post(
    "/",
    response_model=DossierResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un nouveau dossier (exercice)",
)
async def create_dossier(
    dossier_in: DossierCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> Dossier:
    """Crée un dossier pour un client donné."""
    # Vérifier que le client existe et appartient à l'org
    client_result = await db.execute(
        select(Client).where(
            Client.id == dossier_in.client_id,
            Client.org_id == current_user.org_id,
            Client.is_deleted.is_(False),
        )
    )
    if not client_result.scalar_one_or_none():
        raise http_404("Client non trouvé")

    # Vérifier l'unicité (le model a une contrainte, mais on peut anticiper)
    existing = await db.execute(
        select(Dossier).where(
            Dossier.client_id == dossier_in.client_id,
            Dossier.exercice == dossier_in.exercice,
            Dossier.is_deleted.is_(False),
        )
    )
    if existing.scalar_one_or_none():
        raise http_400("Ce dossier (exercice) existe déjà pour ce client")

    dossier = Dossier(**dossier_in.model_dump(), org_id=current_user.org_id)
    db.add(dossier)
    await commit_and_restore_rls_context(db, org_id=current_user.org_id, user_id=current_user.id)
    await db.refresh(dossier)
    logger.info("dossier_created", dossier_id=str(dossier.id), client_id=str(dossier.client_id))
    return dossier


@router.get(
    "/{dossier_id}",
    response_model=DossierResponse,
    status_code=status.HTTP_200_OK,
    summary="Détails d'un dossier",
)
async def get_dossier(
    dossier_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> Dossier:
    result = await db.execute(
        select(Dossier).where(
            Dossier.id == dossier_id,
            Dossier.org_id == current_user.org_id,
            Dossier.is_deleted.is_(False),
        )
    )
    dossier = result.scalar_one_or_none()
    if not dossier:
        raise http_404("Dossier non trouvé")
    return dossier


@router.delete(
    "/{dossier_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Supprimer un dossier",
)
async def delete_dossier(
    dossier_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    result = await db.execute(
        select(Dossier).where(
            Dossier.id == dossier_id,
            Dossier.org_id == current_user.org_id,
            Dossier.is_deleted.is_(False),
        )
    )
    dossier = result.scalar_one_or_none()
    if not dossier:
        raise http_404("Dossier non trouvé")

    dossier.is_deleted = True
    from datetime import UTC, datetime

    dossier.deleted_at = datetime.now(UTC)

    await db.commit()
    logger.info("dossier_deleted", dossier_id=str(dossier_id))
