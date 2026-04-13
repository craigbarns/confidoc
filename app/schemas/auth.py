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


class BootstrapAdminRequest(BaseModel):
    email: EmailStr
    password: str
    first_name: str = "Super"
    last_name: str = "Admin"
    bootstrap_secret: str = ""  # Requis en production (voir BOOTSTRAP_SECRET env var)
