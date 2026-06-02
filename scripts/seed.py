"""Création des rôles par défaut et de l'utilisateur admin."""

import asyncio
import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import async_session_factory
from app.core.security import get_password_hash
from app.models.role import Role
from app.models.user import User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rôles système globaux (org_id is null)
SYSTEM_ROLES = [
    {
        "name": "owner",
        "permissions": ["*"],
        "is_system": True,
    },
    {
        "name": "admin",
        "permissions": [
            "org.manage",
            "members.manage",
            "policies.manage",
            "documents.*",
            "exports.*",
            "audit.read",
        ],
        "is_system": True,
    },
    {
        "name": "member",
        "permissions": [
            "documents.upload",
            "documents.read",
            "documents.raw",
            "documents.process",
            "documents.validate",
            "documents.metadata",
            "detections.manage",
            "exports.create",
            "exports.download",
            "audit.read",
        ],
        "is_system": True,
    },
    {
        "name": "operator",
        "permissions": [
            "documents.upload",
            "documents.read",
            "documents.raw",
            "documents.process",
            "documents.validate",
            "documents.metadata",
            "detections.manage",
            "exports.create",
            "exports.download",
            "audit.read",
        ],
        "is_system": True,
    },
    {
        "name": "viewer",
        "permissions": [
            "documents.read",
            "exports.download",
        ],
        "is_system": True,
    },
    {
        "name": "auditor",
        "permissions": [
            "documents.read",
            "audit.read",
            "audit.export",
            "exports.read",
        ],
        "is_system": True,
    },
]


async def create_system_roles(db: AsyncSession) -> None:
    """Crée les rôles par défaut s'ils n'existent pas."""
    for role_data in SYSTEM_ROLES:
        result = await db.execute(
            select(Role).where(Role.name == role_data["name"], Role.org_id.is_(None))
        )
        existing_role = result.scalars().first()

        if not existing_role:
            logger.info(f"Création du rôle système: {role_data['name']}")
            role = Role(**role_data)
            db.add(role)
        else:
            # Update permissions just in case
            logger.info(f"Mise à jour du rôle système: {role_data['name']}")
            existing_role.permissions = role_data["permissions"]

    await db.commit()


async def create_superadmin(db: AsyncSession) -> None:
    """Crée l'utilisateur superadmin s'il n'existe pas."""
    email = os.getenv("CONFIDOC_SEED_ADMIN_EMAIL", "admin@confidoc.fr")
    result = await db.execute(select(User).where(User.email == email))
    admin = result.scalars().first()

    if not admin:
        password = os.getenv("CONFIDOC_SEED_ADMIN_PASSWORD")
        app_env = os.getenv("APP_ENV", "development").strip().lower()
        if not password:
            if app_env in {"prod", "production"}:
                raise RuntimeError(
                    "CONFIDOC_SEED_ADMIN_PASSWORD is required when seeding production."
                )
            logger.warning(
                "CONFIDOC_SEED_ADMIN_PASSWORD absent; using development-only seed password."
            )
            password = "Admin123!"

        logger.info(f"Création de l'utilisateur admin: {email}")
        user = User(
            email=email,
            password_hash=get_password_hash(password),
            first_name="Super",
            last_name="Admin",
            is_active=True,
            is_platform_admin=True,
        )
        db.add(user)
        await db.commit()
    else:
        logger.info(f"L'utilisateur admin {email} existe déjà.")


async def main() -> None:
    logger.info("Démarrage du script de seed...")
    async with async_session_factory() as session:
        await create_system_roles(session)
        await create_superadmin(session)
    logger.info("Seed terminé avec succès.")


if __name__ == "__main__":
    asyncio.run(main())
