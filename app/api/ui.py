"""ConfiDoc Backend — UI Console premium (refactorisée)."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["ui"])

_TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "index.html"


@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
async def upload_ui() -> HTMLResponse:
    """Interface web ConfiDoc — Console premium."""
    html_content = _TEMPLATE.read_text(encoding="utf-8")
    return HTMLResponse(
        content=html_content,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )
