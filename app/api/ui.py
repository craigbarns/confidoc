"""ConfiDoc Backend — UI Console premium (refactorisee)."""

import asyncio
import os
from html import escape
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from sqlalchemy import distinct, func, select
from starlette.requests import Request

from app.config import get_settings
from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.models.beta_lead import BetaLead

router = APIRouter(tags=["ui"])
logger = get_logger(__name__)
settings = get_settings()

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_TEMPLATE = _TEMPLATE_DIR / "index.html"
_SECURITY_TEMPLATE = _TEMPLATE_DIR / "security.html"
_LANDING_TEMPLATE = _TEMPLATE_DIR / "landing.html"


def _public_base_url(request: Request) -> str:
    configured = str(getattr(settings, "APP_BASE_URL", "") or "").strip().rstrip("/")
    request_base = str(request.base_url).rstrip("/")
    if configured and configured not in {"http://localhost:3000", "http://127.0.0.1:3000"}:
        return configured
    return request_base


def _absolute_url(base_url: str, path: str) -> str:
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base_url}{path}"


def _build_meta_context(
    request: Request,
    *,
    title: str,
    description: str,
    path: str,
    type_: str = "website",
) -> dict[str, str]:
    base_url = _public_base_url(request)
    page_url = _absolute_url(base_url, path)
    og_image_url = _absolute_url(base_url, "/static/confidoc-og-card.png")
    return {
        "PAGE_TITLE": title,
        "META_DESCRIPTION": description,
        "CANONICAL_URL": page_url,
        "OG_URL": page_url,
        "OG_TITLE": title,
        "OG_DESCRIPTION": description,
        "OG_IMAGE_URL": og_image_url,
        "OG_IMAGE_ALT": "ConfiDoc social card",
        "OG_TYPE": type_,
        "TWITTER_TITLE": title,
        "TWITTER_DESCRIPTION": description,
        "TWITTER_IMAGE_URL": og_image_url,
        "PUBLIC_BASE_URL": base_url,
    }


def _ui_version_context() -> dict[str, str]:
    commit_sha = (
        os.getenv("RAILWAY_GIT_COMMIT_SHA")
        or os.getenv("SOURCE_VERSION")
        or os.getenv("BUILD_VERSION")
        or ""
    ).strip()
    short_sha = commit_sha[:7] if commit_sha else "local"
    if short_sha == "local":
        import time
        asset_version = f"local-{int(time.time())}"
    else:
        asset_version = short_sha
    return {
        "ASSET_VERSION": asset_version,
        "UI_VERSION_LABEL": f"{settings.APP_VERSION} · {short_sha}",
    }


async def _get_landing_social_proof() -> dict[str, Any]:
    fallback = {
        "PILOT_EYEBROW": "Programme pilote",
        "PILOT_HEADLINE": "Ouverture progressive aux cabinets qualifies",
        "PILOT_SUPPORTING": (
            "Les acces beta sont ouverts au fil des cas d'usage qualifies. "
            "Aucun chiffre marketing n'est affiche tant qu'il n'est pas mesure."
        ),
        "PILOT_METRIC_1_VALUE": "Selection",
        "PILOT_METRIC_1_LABEL": "qualification manuelle des demandes",
        "PILOT_METRIC_2_VALUE": "RGPD",
        "PILOT_METRIC_2_LABEL": "preuve DPO et export gate des le pilote",
        "PILOT_METRIC_3_VALUE": "Live",
        "PILOT_METRIC_3_LABEL": "demo publique disponible sans login",
    }

    async def _load_counts() -> tuple[int, int]:
        async with async_session_factory() as db:
            result = await db.execute(
                select(
                    func.count(BetaLead.id),
                    func.count(distinct(BetaLead.company)),
                )
            )
            total_leads, total_companies = result.one()
        return int(total_leads or 0), int(total_companies or 0)

    try:
        leads, companies = await asyncio.wait_for(_load_counts(), timeout=0.35)
    except Exception as exc:
        logger.debug("landing_social_proof_unavailable", error=str(exc))
        return fallback

    if leads <= 0 or companies <= 0:
        return fallback

    return {
        "PILOT_EYEBROW": "Signal pilote mesure",
        "PILOT_HEADLINE": f"{companies} cabinets ont deja demande un acces pilote",
        "PILOT_SUPPORTING": (
            "Compteur alimente par les demandes beta recues via la landing publique, "
            "avec qualification manuelle par cas d'usage."
        ),
        "PILOT_METRIC_1_VALUE": str(companies),
        "PILOT_METRIC_1_LABEL": "structures distinctes interessees",
        "PILOT_METRIC_2_VALUE": str(leads),
        "PILOT_METRIC_2_LABEL": "demandes beta qualifiees recues",
        "PILOT_METRIC_3_VALUE": "Manuel",
        "PILOT_METRIC_3_LABEL": "selection sur volume documentaire et use case",
    }


def _render_template(
    template_path: Path,
    request: Request,
    nonce: str,
    context: dict[str, Any] | None = None,
) -> str:
    html_content = template_path.read_text(encoding="utf-8")
    replacements = {"CSP_NONCE": nonce or ""}
    if context:
        replacements.update(
            {key: "" if value is None else str(value) for key, value in context.items()}
        )

    for key, value in replacements.items():
        if key.startswith("RAW_") or key == "CSP_NONCE":
            html_content = html_content.replace(f"{{{{{key}}}}}", value)
        else:
            html_content = html_content.replace(f"{{{{{key}}}}}", escape(value, quote=True))
    return html_content


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def landing_page(request: Request) -> HTMLResponse:
    """Landing page for investors and prospects."""
    nonce = getattr(request.state, "csp_nonce", "")
    context = _build_meta_context(
        request,
        title="ConfiDoc | IA documentaire RGPD pour experts-comptables et avocats",
        description=(
            "Analysez bilans, liasses et contrats avec l'IA sans exposer les donnees "
            "sensibles. Demo publique, Trust Center et preuve DPO telechargeable."
        ),
        path="/",
    )
    context.update(await _get_landing_social_proof())
    html_content = _render_template(_LANDING_TEMPLATE, request, nonce, context)
    return HTMLResponse(
        content=html_content,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
async def upload_ui(request: Request) -> HTMLResponse:
    """Interface web ConfiDoc -- Console premium."""
    nonce = getattr(request.state, "csp_nonce", "")
    context = _build_meta_context(
        request,
        title="ConfiDoc | Console securisee",
        description=(
            "Console securisee ConfiDoc pour traiter, anonymiser et auditer des "
            "documents sensibles en conformite RGPD."
        ),
        path="/ui",
    )
    context.update(_ui_version_context())
    html_content = _render_template(_TEMPLATE, request, nonce, context)
    return HTMLResponse(
        content=html_content,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@router.get("/security", response_class=HTMLResponse, include_in_schema=False)
async def security_page(request: Request) -> HTMLResponse:
    """Page Securite & Conformite RGPD."""
    nonce = getattr(request.state, "csp_nonce", "")
    context = _build_meta_context(
        request,
        title="ConfiDoc Trust Center | Securite, gouvernance IA et conformite RGPD",
        description=(
            "Consultez l'architecture de securite ConfiDoc, les modes d'anonymisation, "
            "le scoring de risque et la preuve DPO telechargeable."
        ),
        path="/trust",
    )
    html_content = _render_template(_SECURITY_TEMPLATE, request, nonce, context)
    return HTMLResponse(
        content=html_content,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@router.get("/trust", response_class=HTMLResponse, include_in_schema=False)
async def trust_center_page(request: Request) -> HTMLResponse:
    """Alias public du Trust Center ConfiDoc."""
    return await security_page(request)


_FIREWALL_TEMPLATE = _TEMPLATE_DIR / "firewall.html"


@router.get("/firewall", response_class=HTMLResponse, include_in_schema=False)
async def firewall_dashboard_page(request: Request) -> HTMLResponse:
    """Tableau de bord DPO/RSSI de l'AI Firewall (public, sans login pour la démo)."""
    nonce = getattr(request.state, "csp_nonce", "")
    context = _build_meta_context(
        request,
        title="ConfiDoc | AI Firewall — Tableau de bord DPO/RSSI",
        description=(
            "Tous les échanges IA sont inspectés en temps réel par l'AI Firewall : "
            "prompts, réponses, redactions, blocages et risques critiques en direct."
        ),
        path="/firewall",
    )
    context.update(_ui_version_context())
    html_content = _render_template(_FIREWALL_TEMPLATE, request, nonce, context)
    return HTMLResponse(
        content=html_content,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


_ARCHITECTURE_TEMPLATE = _TEMPLATE_DIR / "architecture.html"

@router.get("/architecture", response_class=HTMLResponse, include_in_schema=False)
async def architecture_page(request: Request) -> HTMLResponse:
    """Page d'architecture interactive du backend ConfiDoc."""
    import json
    
    # 1. Calcul dynamique des métriques de modularité
    def _count_py_files(subdir: str) -> int:
        try:
            p = Path(__file__).resolve().parent.parent / subdir
            if not p.exists():
                return 0
            return len([
                f for f in p.glob("**/*.py") 
                if f.name != "__init__.py" and "__pycache__" not in str(f)
            ])
        except Exception:
            return 0

    metrics = {
        "services_count": _count_py_files("services"),
        "models_count": _count_py_files("models"),
        "schemas_count": _count_py_files("schemas"),
        "api_v1_count": _count_py_files("api/v1"),
    }

    # 2. Scan et extraction dynamique des routes FastAPI
    routes_data = []
    for route in request.app.routes:
        # Exclure les routes internes du schéma openapi ou les routes de redirection techniques
        if route.path in {"/openapi.json", "/docs", "/redoc", "/metrics"}:
            continue
            
        methods = list(route.methods) if hasattr(route, "methods") and route.methods else []
        clean_methods = [m for m in methods if m not in {"HEAD", "OPTIONS"}]
        if not clean_methods and not route.path.startswith("/static"):
            clean_methods = ["GET"]

        docstring = ""
        if hasattr(route, "endpoint") and route.endpoint:
            docstring = route.endpoint.__doc__ or ""
            docstring = docstring.strip().replace("\n", " ")

        tags = list(route.tags) if hasattr(route, "tags") and route.tags else []
        if not tags:
            if route.path.startswith("/api/v1/auth"):
                tags = ["auth"]
            elif route.path.startswith("/api/v1/uploads"):
                tags = ["uploads"]
            elif route.path.startswith("/api/v1/documents"):
                tags = ["documents"]
            elif route.path.startswith("/api/v1/copilot") or route.path.startswith("/api/v1/ai"):
                tags = ["ai"]
            elif route.path.startswith("/api/v1/compliance"):
                tags = ["compliance"]
            elif route.path.startswith("/api/v1/integrations"):
                tags = ["integrations"]
            elif route.path.startswith("/api/v1/leads"):
                tags = ["leads"]
            elif route.path.startswith("/ui") or route.path == "/":
                tags = ["ui"]
            else:
                tags = ["system"]

        routes_data.append({
            "path": route.path,
            "methods": clean_methods,
            "name": route.name or "",
            "description": docstring,
            "tag": tags[0] if tags else "system"
        })

    routes_data.sort(key=lambda r: r["path"])

    # 3. Préparation du contexte
    nonce = getattr(request.state, "csp_nonce", "")
    meta_context = _build_meta_context(
        request,
        title="ConfiDoc | Architecture & Developer Hub",
        description="Explorateur d'API dynamique, cartographie Mermaid.js du pipeline d'anonymisation et métriques de santé du backend ConfiDoc.",
        path="/architecture",
    )

    context = {
        "RAW_ROUTES_JSON": json.dumps(routes_data),
        "RAW_METRICS_JSON": json.dumps(metrics),
        "SERVICES_COUNT": str(metrics["services_count"]),
        "MODELS_COUNT": str(metrics["models_count"]),
        "SCHEMAS_COUNT": str(metrics["schemas_count"]),
        "API_V1_COUNT": str(metrics["api_v1_count"]),
    }
    context.update(meta_context)

    html_content = _render_template(_ARCHITECTURE_TEMPLATE, request, nonce, context)
    return HTMLResponse(
        content=html_content,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )
