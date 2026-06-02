"""PDF report generation for Dossier 360 portfolio summaries (Premium Version)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fpdf import FPDF

# Modern Enterprise Colors
_PRIMARY = (17, 24, 39)  # Gray 900
_SECONDARY = (79, 70, 229)  # Indigo 600
_ACCENT = (99, 102, 241)  # Indigo 500
_MUTED = (107, 114, 128)  # Gray 500
_LIGHT_BG = (249, 250, 251)  # Gray 50
_BORDER = (229, 231, 235)  # Gray 200

# Status Colors
_SUCCESS = (16, 185, 129)  # Emerald 500
_WARNING = (245, 158, 11)  # Amber 500
_DANGER = (239, 68, 68)  # Red 500

_RISK_COLORS = {
    "low": _SUCCESS,
    "medium": _WARNING,
    "high": _DANGER,
    "critical": _DANGER,
}

_RISK_LABELS = {
    "low": "Risque Faible",
    "medium": "Risque Moyen",
    "high": "Risque Élevé",
    "critical": "Risque Critique",
}


def _safe(value: object) -> str:
    """Keep PDF text compatible with built-in Helvetica fonts."""
    text = str(value or "")
    return text.encode("latin-1", "replace").decode("latin-1")


class _PremiumDossierPDF(FPDF):
    def __init__(self) -> None:
        super().__init__()
        self.set_auto_page_break(auto=True, margin=20)

    def header(self) -> None:
        # Cover page has no header
        if self.page_no() == 1:
            return

        self.set_fill_color(*_LIGHT_BG)
        self.rect(0, 0, 210, 25, "F")
        self.set_draw_color(*_BORDER)
        self.line(0, 25, 210, 25)

        self.set_xy(15, 8)
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(*_PRIMARY)
        self.cell(0, 7, "ConfiDoc Enterprise", new_x="LMARGIN")

        self.set_xy(15, 15)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*_MUTED)
        self.cell(0, 5, "Bilan de Conformite RGPD & Revue de Portefeuille", new_x="LMARGIN")

        self.set_xy(135, 10)
        now = datetime.now(UTC).strftime("%d/%m/%Y %H:%M")
        self.set_font("Helvetica", "", 8)
        self.cell(60, 5, _safe(f"Genere le {now} UTC"), align="R")
        self.set_y(35)

    def footer(self) -> None:
        # Cover page has no footer
        if self.page_no() == 1:
            return

        self.set_y(-15)
        self.set_draw_color(*_BORDER)
        self.line(15, self.get_y(), 195, self.get_y())

        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*_MUTED)
        self.cell(0, 9, f"Confidentiel -- Dossier 360 -- Page {self.page_no()}/{{nb}}", align="C")

    def draw_cover(self, portfolio: dict[str, Any]) -> None:
        """Dessine une page de garde premium."""
        self.add_page()

        # Top banner
        self.set_fill_color(*_PRIMARY)
        self.rect(0, 0, 210, 80, "F")

        self.set_xy(15, 30)
        self.set_font("Helvetica", "B", 28)
        self.set_text_color(255, 255, 255)
        self.multi_cell(180, 12, "BILAN DE CONFORMITE\nRGPD & DOSSIER 360", align="L")

        self.set_xy(15, 60)
        self.set_font("Helvetica", "", 12)
        self.set_text_color(209, 213, 219)
        self.cell(180, 6, "Rapport d'Audit Automatique", new_x="LMARGIN", new_y="NEXT")

        self.set_y(100)

        # Summary Box
        self.set_fill_color(*_LIGHT_BG)
        self.set_draw_color(*_BORDER)
        self.rect(15, 95, 180, 50, "DF")

        self.set_xy(20, 100)
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(*_PRIMARY)
        self.cell(0, 8, "Resume Executif", new_x="LMARGIN", new_y="NEXT")

        self.set_font("Helvetica", "", 10)
        self.set_text_color(*_MUTED)
        summary = (
            f"Ce rapport consolide l'etat de preparation de vos dossiers clients. "
            f"Il inclut l'analyse de {portfolio.get('documents_count', 0)} documents repartis "
            f"sur {portfolio.get('clients_count', 0)} clients. L'objectif est d'identifier "
            "rapidement les pieces manquantes et les risques de re-identification avant tout "
            "export ou audit."
        )
        self.set_x(20)
        self.multi_cell(170, 6, _safe(summary))

        # Score Highlight
        self.set_y(160)
        average_score = int(portfolio.get("average_score") or 0)
        score_color = _score_color(average_score)

        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*_PRIMARY)
        self.cell(180, 8, "Score de Conformite Moyen", align="C", new_x="LMARGIN", new_y="NEXT")

        self.set_font("Helvetica", "B", 48)
        self.set_text_color(*score_color)
        self.cell(180, 20, f"{average_score}/100", align="C", new_x="LMARGIN", new_y="NEXT")

        self.add_page()  # Start content on page 2

    def section_title(self, title: str) -> None:
        self.ln(6)
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(*_PRIMARY)
        self.cell(0, 8, _safe(title), new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*_ACCENT)
        self.line(self.get_x(), self.get_y(), self.get_x() + 30, self.get_y())
        self.ln(5)

    def metric_card(
        self, x: float, y: float, title: str, value: object, color: tuple[int, int, int]
    ) -> None:
        self.set_fill_color(255, 255, 255)
        self.set_draw_color(*_BORDER)
        self.rect(x, y, 42, 26, "DF")
        self.set_xy(x + 4, y + 4)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*_MUTED)
        self.cell(34, 4, _safe(title), new_x="LMARGIN")
        self.set_xy(x + 4, y + 12)
        self.set_font("Helvetica", "B", 18)
        self.set_text_color(*color)
        self.cell(34, 8, _safe(value), new_x="LMARGIN")


def _score_color(score: int) -> tuple[int, int, int]:
    if score >= 80:
        return _SUCCESS
    if score >= 60:
        return _WARNING
    return _DANGER


def _bullet_list(pdf: _PremiumDossierPDF, items: list[Any], *, limit: int = 4) -> None:
    if not items:
        pdf.set_text_color(*_MUTED)
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(0, 5, "Aucun element prioritaire detecte.", new_x="LMARGIN", new_y="NEXT")
        return
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*_PRIMARY)
    for item in items[:limit]:
        pdf.set_x(pdf.get_x() + 5)
        pdf.multi_cell(0, 5, _safe(f"• {item}"))
        pdf.set_x(pdf.get_x() - 5)


def generate_dossier_360_pdf(payload: dict[str, Any]) -> bytes:
    """Generate a Premium PDF portfolio report."""

    portfolio = payload.get("portfolio") or {}
    dossiers = payload.get("dossiers") or []

    pdf = _PremiumDossierPDF()
    pdf.alias_nb_pages()

    # Page 1 : Cover
    pdf.draw_cover(portfolio)

    # Page 2 : Overview Metrics
    pdf.section_title("1. Metriques Globales")
    start_y = pdf.get_y()

    metrics = [
        ("Total Clients", portfolio.get("clients_count", 0), _SECONDARY),
        ("Total Documents", portfolio.get("documents_count", 0), _SECONDARY),
        ("Dossiers Prets", portfolio.get("ready_dossiers", 0), _SUCCESS),
        ("Dossiers a Risque", portfolio.get("at_risk_dossiers", 0), _DANGER),
    ]
    for idx, (title, value, color) in enumerate(metrics):
        pdf.metric_card(15 + idx * 45, start_y, title, value, color)
    pdf.set_y(start_y + 35)

    missing = portfolio.get("top_missing_documents") or []
    if missing:
        pdf.section_title("2. Top 5 Pieces Manquantes (Vue Portefeuille)")
        pdf.set_fill_color(*_LIGHT_BG)
        pdf.set_draw_color(*_BORDER)
        pdf.rect(15, pdf.get_y(), 180, len(missing[:5]) * 8 + 4, "DF")
        pdf.set_y(pdf.get_y() + 2)
        for item in missing[:5]:
            label = item.get("label", "Piece") if isinstance(item, dict) else str(item)
            count = item.get("count", 0) if isinstance(item, dict) else ""
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(*_PRIMARY)
            pdf.set_x(20)
            pdf.cell(140, 8, _safe(f"• {label}"))
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(*_WARNING)
            pdf.cell(30, 8, _safe(f"{count} manquant(s)"), align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(6)

    # Page 3+ : Detailed Dossiers
    pdf.add_page()
    pdf.section_title("3. Revues Individuelles des Dossiers")

    if not dossiers:
        pdf.set_font("Helvetica", "I", 10)
        pdf.set_text_color(*_MUTED)
        pdf.cell(0, 6, "Aucun dossier client disponible.", new_x="LMARGIN", new_y="NEXT")

    for idx, dossier in enumerate(dossiers[:15], 1):
        if pdf.get_y() > 210:
            pdf.add_page()

        y = pdf.get_y()
        score = int(dossier.get("score") or 0)
        risk = str(dossier.get("risk_level") or "low")
        risk_color = _RISK_COLORS.get(risk, _MUTED)

        # Dossier Header Box
        pdf.set_fill_color(*_LIGHT_BG)
        pdf.set_draw_color(*_BORDER)
        pdf.rect(15, y, 180, 14, "DF")

        pdf.set_xy(18, y + 4)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*_PRIMARY)
        client = dossier.get("client_name") or "Sans client"
        readiness = dossier.get("readiness") or ""
        pdf.cell(100, 6, _safe(f"{idx}. {client}"))

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*_MUTED)
        pdf.cell(40, 6, _safe(readiness))

        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*_score_color(score))
        pdf.cell(15, 6, f"{score}/100", align="R")

        pdf.set_text_color(*risk_color)
        pdf.cell(22, 6, _safe(_RISK_LABELS.get(risk, risk)), align="R")

        pdf.set_y(y + 18)

        # Internal Box Content
        ready_count = dossier.get("ready_count", 0)
        document_count = dossier.get("document_count", 0)
        entities = dossier.get("entity_count", 0)

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*_PRIMARY)
        pdf.cell(
            0,
            6,
            _safe(
                f"Documents prets : {ready_count}/{document_count}  |  Entites masquees : {entities}"
            ),
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.ln(2)

        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*_WARNING)
        pdf.cell(0, 6, "Pieces manquantes :", new_x="LMARGIN", new_y="NEXT")
        _bullet_list(pdf, list(dossier.get("missing_documents") or []), limit=3)
        pdf.ln(2)

        blockers = list(dossier.get("blockers") or [])
        if blockers:
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(*_DANGER)
            pdf.cell(0, 6, "Blockers / Risques critiques :", new_x="LMARGIN", new_y="NEXT")
            _bullet_list(pdf, blockers, limit=3)
            pdf.ln(2)

        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*_SECONDARY)
        pdf.cell(0, 6, "Prochaines actions :", new_x="LMARGIN", new_y="NEXT")
        _bullet_list(pdf, list(dossier.get("next_actions") or []), limit=3)

        pdf.ln(8)
        pdf.set_draw_color(243, 244, 246)
        pdf.line(15, pdf.get_y(), 195, pdf.get_y())
        pdf.ln(4)

    return bytes(pdf.output(dest="S"))
