"""ConfiDoc Backend — Repository Dependencies."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.repositories.document_repository import DocumentRepository


async def get_document_repository(
    db: AsyncSession = Depends(get_db)
) -> DocumentRepository:
    """Dependency provider for DocumentRepository."""
    return DocumentRepository(db)
