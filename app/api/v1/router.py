"""ConfiDoc Backend — API v1 router principal."""

from fastapi import APIRouter

router = APIRouter()

from app.api.v1 import auth, documents, kb, uploads, users

router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
router.include_router(documents.router, prefix="/documents", tags=["documents"])
router.include_router(kb.router, prefix="/kb", tags=["kb"])
