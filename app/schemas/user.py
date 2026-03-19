"""ConfiDoc Backend — Schemas User."""

from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr
    first_name: str = Field(..., max_length=100)
    last_name: str = Field(..., max_length=100)


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, description="Mot de passe fort")


class UserUpdate(BaseModel):
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    # email: Le changement d'email demande un flow spécial
    # password: Le changement mdp demande un endpoint spécial


class UserResponse(UserBase):
    id: uuid.UUID
    is_active: bool
    is_platform_admin: bool
    last_login_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MemberResponse(BaseModel):
    """Réponse quand on liste les membres d'une organisation."""
    user: UserResponse
    role_name: str
    joined_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)
