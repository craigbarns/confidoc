"""ConfiDoc Backend — UI Console premium (refactorisee)."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from starlette.requests import Request

router = APIRouter(tags=["ui"])

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_TEMPLATE = _TEMPLATE_DIR / "index.html"
_SECURITY_TEMPLATE = _TEMPLATE_DIR / "security.html"
_LANDING_TEMPLATE = _TEMPLATE_DIR / "landing.html"


def _render_template(template_path: Path, request: Request, nonce: str) -> str:
    html_content = template_path.read_text(encoding="utf-8")
    if nonce:
        html_content = html_content.replace('{{CSP_NONCE}}', nonce)
    return html_content


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def landing_page(request: Request) -> HTMLResponse:
    """Landing page for investors and prospects."""
    nonce = getattr(request.state, "csp_nonce", "")
    html_content = _render_template(_LANDING_TEMPLATE, request, nonce)
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
    html_content = _render_template(_TEMPLATE, request, nonce)
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
    html_content = _render_template(_SECURITY_TEMPLATE, request, nonce)
    return HTMLResponse(
        content=html_content,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )
