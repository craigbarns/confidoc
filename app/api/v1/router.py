"""ConfiDoc Backend — API v1 router principal."""

from fastapi import APIRouter

from app.api.v1 import ai, auth, copilot, demo, documents, leads, uploads, users

router = APIRouter()

router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
router.include_router(documents.router, prefix="/documents", tags=["documents"])
router.include_router(ai.router, prefix="/ai", tags=["ai"])
router.include_router(copilot.router, prefix="/copilot", tags=["copilot"])
router.include_router(demo.router, prefix="/demo", tags=["demo"])
router.include_router(leads.router, prefix="/leads", tags=["leads"])
