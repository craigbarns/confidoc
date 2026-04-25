"""ConfiDoc Backend — Base Repository (Generic CRUD)."""

from typing import Any, Generic, TypeVar, Sequence
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Generic base repository for common CRUD operations."""

    def __init__(self, model: type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session

    async def get(self, id: UUID | str) -> ModelType | None:
        """Get a single record by its ID."""
        if isinstance(id, str):
            id = UUID(id)
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def get_multi(
        self, *, skip: int = 0, limit: int = 100
    ) -> Sequence[ModelType]:
        """Get multiple records with pagination."""
        result = await self.session.execute(
            select(self.model).offset(skip).limit(limit)
        )
        return result.scalars().all()

    async def create(self, *, obj_in: dict[str, Any]) -> ModelType:
        """Create a new record."""
        db_obj = self.model(**obj_in)
        self.session.add(db_obj)
        await self.session.flush()
        return db_obj

    async def update(
        self, *, db_obj: ModelType, obj_in: dict[str, Any]
    ) -> ModelType:
        """Update an existing record."""
        for field, value in obj_in.items():
            setattr(db_obj, field, value)
        self.session.add(db_obj)
        await self.session.flush()
        return db_obj

    async def remove(self, *, id: UUID | str) -> ModelType | None:
        """Remove a record by its ID."""
        if isinstance(id, str):
            id = UUID(id)
        obj = await self.get(id)
        if obj:
            await self.session.delete(obj)
            await self.session.flush()
        return obj

    async def delete_by_id(self, id: UUID | str) -> bool:
        """Delete a record by ID without loading it first."""
        if isinstance(id, str):
            id = UUID(id)
        result = await self.session.execute(
            delete(self.model).where(self.model.id == id)
        )
        return result.rowcount > 0
