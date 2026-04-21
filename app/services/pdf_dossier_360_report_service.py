"""PDF report generation for Dossier 360 portfolio summaries."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fpdf import FPDF

_ACCENT = (93, 95, 239)
_DARK = (15, 17, 23)
_WHITE = (255, 255, 255)
_MUTED = (109, 116, 145)
_LIGHT = (244, 246, 251)
_SUCCESS = (16, 185, 129)
_WARNING = (245, 158, 11)
_DANGER = (239, 68, 68)

_RISK_COLORS = {
    "low": _SUCCESS,
    "medium": _WARNING,
    "high": _DANGER,
    "critical": _DANGER,
}
_RISK_LABELS = {
    "low": "Faible",
    "medium": "Moyen",
    "high": "Eleve",
    "critical": "Critique",
}


def _safe(value: object) -> str:
    """Keep PDF text compatible with built-in Helvetica fonts."""
    text = str(value or "")
    return text.encode("latin-1", "replace").decode("latin-1")


class _Dossier360PDF(FPDF):
    def __init__(self) -> None:
        super().__init__()
        self.set_auto_page_break(auto=True, margin=20)

    def header(self) -> None:
        self.set_fill_color(*_DARK)
        self.rect(0, 0, 210, 30, "F")
        self.set_xy(12, 7)
        self.set_font("Helvetica", "B", 17)
        self.set_text_color(*_WHITE)
        self.cell(0, 7, "ConfiDoc", new_x="LMARGIN")
        self.set_xy(12, 16)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(185, 191, 215)
        self.cell(0, 6, "Rapport Dossier 360", new_x="LMARGIN")
        self.set_xy(135, 8)
        now = datetime.now(UTC).strftime("%d/%m/%Y %H:%M UTC")
        self.set_font("Helvetica", "", 8)
        self.cell(63, 5, _safe(f"Genere le {now}"), align="R")
        self.set_y(36)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_draw_color(*_ACCENT)
        self.line(10, self.get_y(), 200, self.get_y())
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(*_MUTED)
        self.cell(0, 9, f"ConfiDoc -- Dossier 360 -- Page {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title: str) -> None:
        self.ln(4)
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(*_ACCENT)
        self.cell(0, 7, _safe(title), new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*_ACCENT)
        self.line(self.get_x(), self.get_y(), self.get_x() + 45, self.get_y())
        self.ln(4)

    def metric_card(self, x: float, title: str, value: object, color: tuple[int, int, int]) -> None:
        y = self.get_y()
        self.set_fill_color(*_LIGHT)
        self.set_draw_color(222, 226, 238)
        self.rect(x, y, 43, 24, "DF")
        self.set_xy(x + 4, y + 4)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*_MUTED)
        self.cell(35, 4, _safe(title), new_x="LMARGIN")
        self.set_xy(x + 4, y + 11)
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(*color)
        self.cell(35, 7, _safe(value), new_x="LMARGIN")


def _score_color(score: int) -> tuple[int, int, int]:
    if score >= 80:
        return _SUCCESS
    if score >= 55:
        return _WARNING
    return _DANGER


def _bullet_list(pdf: _Dossier360PDF, items: list[Any], *, limit: int = 4) -> None:
    if not items:
        pdf.set_text_color(*_MUTED)
        pdf.set_font("Helvetica", "I", 8)
        pdf.cell(0, 5, "Aucun element prioritaire.", new_x="LMARGIN", new_y="NEXT")
        return
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(45, 48, 70)
    for item in items[:limit]:
        pdf.multi_cell(0, 4.5, _safe(f"- {item}"))


def generate_dossier_360_pdf(payload: dict[str, Any]) -> bytes:
    """Generate a PDF portfolio report from a Dossier 360 payload."""

    portfolio = payload.get("portfolio") or {}
    dossiers = payload.get("dossiers") or []

    pdf = _Dossier360PDF()
    pdf.alias_nb_pages()
    pdf.add_page()

    pdf.section_title("1. Synthese portefeuille")
    start_y = pdf.get_y()
    average_score = int(portfolio.get("average_score") or 0)
    metrics = [
        ("Clients", portfolio.get("clients_count", 0), _ACCENT),
        ("Score moyen", f"{average_score}/100", _score_color(average_score)),
        ("Dossiers prets", portfolio.get("ready_dossiers", 0), _SUCCESS),
        ("Dossiers a risque", portfolio.get("at_risk_dossiers", 0), _DANGER),
    ]
    for idx, (title, value, color) in enumerate(metrics):
        pdf.metric_card(12 + idx * 47, title, value, color)
    pdf.set_y(start_y + 29)

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(45, 48, 70)
    summary = (
        f"{portfolio.get('documents_count', 0)} document(s) analyses, "
        f"{portfolio.get('critical_actions', 0)} action(s) critique(s) identifiees. "
        "Ce rapport priorise les dossiers clients selon leur preparation, leur risque "
        "et les pieces manquantes."
    )
    pdf.multi_cell(0, 5, _safe(summary))

    missing = portfolio.get("top_missing_documents") or []
    if missing:
        pdf.section_title("2. Pieces manquantes recurrentes")
        for item in missing[:5]:
            label = item.get("label", "Piece") if isinstance(item, dict) else str(item)
            count = item.get("count", 0) if isinstance(item, dict) else ""
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(45, 48, 70)
            pdf.cell(0, 5, _safe(f"- {label} ({count} dossier(s))"), new_x="LMARGIN", new_y="NEXT")

    pdf.section_title("3. Dossiers prioritaires")
    if not dossiers:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*_MUTED)
        pdf.cell(0, 6, "Aucun dossier client disponible.", new_x="LMARGIN", new_y="NEXT")
    for idx, dossier in enumerate(dossiers[:8], 1):
        score = int(dossier.get("score") or 0)
        risk = str(dossier.get("risk_level") or "low")
        risk_color = _RISK_COLORS.get(risk, _MUTED)

        if pdf.get_y() > 238:
            pdf.add_page()

        y = pdf.get_y()
        pdf.set_fill_color(*_LIGHT)
        pdf.set_draw_color(222, 226, 238)
        pdf.rect(12, y, 186, 12, "DF")
        pdf.set_xy(15, y + 3)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*_DARK)
        client = dossier.get("client_name") or "Sans client"
        readiness = dossier.get("readiness") or ""
        pdf.cell(110, 5, _safe(f"{idx}. {client} -- {readiness}"))
        pdf.set_xy(143, y + 3)
        pdf.set_text_color(*_score_color(score))
        pdf.cell(25, 5, f"{score}/100")
        pdf.set_text_color(*risk_color)
        pdf.cell(25, 5, _safe(_RISK_LABELS.get(risk, risk)), align="R")
        pdf.set_y(y + 16)

        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*_MUTED)
        ready_count = dossier.get("ready_count", 0)
        document_count = dossier.get("document_count", 0)
        pdf.cell(
            0,
            5,
            _safe(
                f"{ready_count}/{document_count} documents prets, "
                f"{dossier.get('entity_count', 0)} entites masquees"
            ),
            new_x="LMARGIN",
            new_y="NEXT",
        )

        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*_ACCENT)
        pdf.cell(0, 5, "Pieces manquantes", new_x="LMARGIN", new_y="NEXT")
        _bullet_list(pdf, list(dossier.get("missing_documents") or []), limit=3)

        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*_WARNING)
        pdf.cell(0, 5, "Blockers", new_x="LMARGIN", new_y="NEXT")
        _bullet_list(pdf, list(dossier.get("blockers") or []), limit=3)

        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*_SUCCESS)
        pdf.cell(0, 5, "Prochaines actions", new_x="LMARGIN", new_y="NEXT")
        _bullet_list(pdf, list(dossier.get("next_actions") or []), limit=3)
        pdf.ln(3)

    pdf.add_page()
    pdf.section_title("4. Lecture cabinet / investisseur")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(45, 48, 70)
    pdf.multi_cell(
        0,
        5,
        _safe(
            "Le Dossier 360 est une synthese operationnelle. Il ne remplace pas la revue "
            "professionnelle, mais permet d'identifier rapidement les dossiers prets, les "
            "risques de re-identification, les pieces a demander et les actions a prioriser."
        ),
    )

    return bytes(pdf.output(dest="S"))
