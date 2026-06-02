"""ConfiDoc Backend — Documents router (assembly).

Ce fichier est le point d'entrée exposé dans v1/router.py.
La logique est répartie en sous-modules :

  _doc_shared.py      — helpers partagés (pas de routes)
  _doc_crud.py        — CRUD : list, get, delete, restore, trash
  _doc_stats.py       — stats dashboard, status-summary
  _doc_processing.py  — extract, anonymize, validate, approve
  _doc_export.py      — export, audit-report, compliance, risk-score
"""

from fastapi import APIRouter

from app.api.v1._doc_crud import router as crud_router
from app.api.v1._doc_dossier import router as dossier_router
from app.api.v1._doc_export import router as export_router
from app.api.v1._doc_processing import router as processing_router
from app.api.v1._doc_stats import router as stats_router

router = APIRouter()

# L'ordre d'inclusion est important : routes statiques avant /{document_id}
router.include_router(stats_router)  # /stats/dashboard, /status-summary
router.include_router(dossier_router)  # /dossiers, /{id}/metadata (avant /{id})
router.include_router(crud_router)  # /, /clients, /trash/list, /all, /{id}
router.include_router(processing_router)  # /{id}/extract, /anonymize, /validate…
router.include_router(export_router)  # /{id}/export, /audit-report, /compliance…
