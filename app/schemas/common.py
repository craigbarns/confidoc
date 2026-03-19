"""ConfiDoc Backend — Schemas communs (Pagination)."""

from typing import Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Format de réponse standard pour la pagination."""

    items: list[T]
    total: int = Field(..., description="Nombre total d'éléments")
    page: int = Field(default=1, description="Page actuelle (1-index)")
    size: int = Field(default=50, description="Taille de la page")
    pages: int = Field(..., description="Nombre total de pages")
