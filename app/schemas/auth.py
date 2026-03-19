"""ConfiDoc Backend — Schemas Auth."""

from pydantic import BaseModel, EmailStr


class TokenResponse(BaseModel):
    """Réponse d'authentification réussie."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str
