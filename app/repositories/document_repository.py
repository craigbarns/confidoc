"""ConfiDoc Backend — Document Repository."""

from uuid import UUID
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus
from app.repositories.base import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    """Repository for managing Document entities."""

    def __init__(self, session: AsyncSession):
        super().__init__(Document, session)

    async def get_by_user(
        self, user_id: UUID | str, *, skip: int = 0, limit: int = 100
    ) -> Sequence[Document]:
        """Get all documents for a specific user."""
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        result = await self.session.execute(
            select(self.model)
            .where(self.model.user_id == user_id, self.model.is_deleted == False)
            .offset(skip)
            .limit(limit)
            .order_by(self.model.created_at.desc())
        )
        return result.scalars().all()

    async def get_by_org(
        self, org_id: UUID | str, *, skip: int = 0, limit: int = 100
    ) -> Sequence[Document]:
        """Get all documents for a specific organization."""
        if isinstance(org_id, str):
            org_id = UUID(org_id)
        result = await self.session.execute(
            select(self.model)
            .where(self.model.org_id == org_id, self.model.is_deleted == False)
            .offset(skip)
            .limit(limit)
            .order_by(self.model.created_at.desc())
        )
        return result.scalars().all()

    async def get_by_id_and_user(
        self, id: UUID | str, user_id: UUID | str
    ) -> Document | None:
        """Get a specific document if it belongs to a specific user."""
        if isinstance(id, str):
            id = UUID(id)
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        result = await self.session.execute(
            select(self.model).where(
                self.model.id == id,
                self.model.user_id == user_id,
                self.model.is_deleted == False,
            )
        )
        return result.scalar_one_or_none()

    async def update_status(self, id: UUID | str, status: DocumentStatus) -> bool:
        """Quickly update document status."""
        if isinstance(id, str):
            id = UUID(id)
        db_obj = await self.get(id)
        if db_obj:
            db_obj.status = status
            self.session.add(db_obj)
            await self.session.flush()
            return True
        return False
