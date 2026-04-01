"""ConfiDoc Backend — UI Console premium (refactorisee)."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["ui"])

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_TEMPLATE = _TEMPLATE_DIR / "index.html"
_SECURITY_TEMPLATE = _TEMPLATE_DIR / "security.html"


@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
async def upload_ui() -> HTMLResponse:
    """Interface web ConfiDoc -- Console premium."""
    html_content = _TEMPLATE.read_text(encoding="utf-8")
    return HTMLResponse(
        content=html_content,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@router.get("/security", response_class=HTMLResponse, include_in_schema=False)
async def security_page() -> HTMLResponse:
    """Page Securite & Conformite RGPD."""
    html_content = _SECURITY_TEMPLATE.read_text(encoding="utf-8")
    return HTMLResponse(
        content=html_content,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )
