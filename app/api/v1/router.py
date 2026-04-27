"""ConfiDoc Backend — API v1 router principal."""

from fastapi import APIRouter

from app.api.v1 import (
    ai,
    auth,
    clients,
    compliance,
    copilot,
    demo,
    documents,
    dossiers,
    integrations,
    leads,
    uploads,
    users,
)
from app.api.v1._doc_stats import router as stats_router

router = APIRouter()

router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(clients.router, prefix="/clients", tags=["clients"])
router.include_router(dossiers.router, prefix="/dossiers", tags=["dossiers"])
router.include_router(compliance.router, prefix="/compliance", tags=["compliance"])
router.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
router.include_router(documents.router, prefix="/documents", tags=["documents"])
router.include_router(stats_router, prefix="/stats", tags=["stats"])
router.include_router(ai.router, prefix="/ai", tags=["ai"])
router.include_router(copilot.router, prefix="/copilot", tags=["copilot"])
router.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
router.include_router(demo.router, prefix="/demo", tags=["demo"])
router.include_router(leads.router, prefix="/leads", tags=["leads"])
