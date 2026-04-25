"""ConfiDoc — Professional RGPD audit report PDF generation.

Generates a branded, premium-grade PDF report with:
- ConfiDoc dark cover page with purple accent stripe
- Document metadata
- Re-identification risk score with visual gauge + badge
- Entity summary table (borderless, alternating rows)
- Chronological audit trail (borderless)
- RGPD compliance statement
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any

from fpdf import FPDF


_PURPLE = (124, 116, 255)
_DARK = (15, 17, 23)
_WHITE = (255, 255, 255)
_GRAY = (163, 171, 199)
_LIGHT_BG = (244, 246, 251)
_SUCCESS = (16, 185, 129)
_WARNING = (245, 158, 11)
_DANGER = (239, 68, 68)
_CRITICAL = (220, 38, 38)

_RISK_COLORS = {
    "low": _SUCCESS,
    "medium": _WARNING,
    "high": _DANGER,
    "critical": _CRITICAL,
}
_RISK_LABELS = {
    "low": "FAIBLE",
    "medium": "MOYEN",
    "high": "ELEVE",
    "critical": "CRITIQUE",
}


class _AuditPDF(FPDF):
    def __init__(self, doc_name: str) -> None:
        super().__init__()
        self._doc_name = doc_name
        self.set_auto_page_break(auto=True, margin=25)

    def header(self) -> None:
        # Skip header on cover page (page 1)
        if self.page_no() == 1:
            return

        # Dark top bar
        self.set_fill_color(*_DARK)
        self.rect(0, 0, 210, 22, "F")
        # Purple accent stripe
        self.set_fill_color(*_PURPLE)
        self.rect(0, 20, 210, 2, "F")

        # ConfiDoc logo
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(*_WHITE)
        self.set_xy(12, 5)
        self.cell(0, 7, "ConfiDoc", new_x="LMARGIN")

        # Subtitle
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*_GRAY)
        self.set_xy(12, 13)
        self.cell(0, 5, "Rapport de Conformite RGPD", new_x="LMARGIN")

        # Date on the right
        self.set_font("Helvetica", "", 8)
        self.set_xy(130, 7)
        self.set_text_color(*_GRAY)
        now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
        self.cell(70, 6, f"Genere le {now}", align="R")

        self.set_xy(15, 30)

    def footer(self) -> None:
        # Skip footer on cover page
        if self.page_no() == 1:
            return

        self.set_y(-18)
        # Purple line
        self.set_draw_color(*_PURPLE)
        self.set_line_width(0.6)
        self.line(10, self.get_y(), 200, self.get_y())
        self.set_line_width(0.2)
        self.ln(2)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*_GRAY)
        self.cell(
            0,
            6,
            f"ConfiDoc -- Rapport confidentiel -- Page {self.page_no()}/{{nb}}",
            align="C",
        )

    def section_title(self, title: str) -> None:
        self.ln(8)
        bar_y = self.get_y()
        # Purple left bar
        self.set_fill_color(*_PURPLE)
        self.rect(10, bar_y, 3, 9, "F")
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*_DARK)
        self.set_xy(16, bar_y)
        self.cell(0, 9, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

    def kv_row(self, key: str, value: str) -> None:
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(80, 80, 100)
        self.cell(60, 7, key, new_x="END")
        self.set_font("Helvetica", "", 9)
        self.set_text_color(30, 30, 50)
        self.cell(0, 7, value, new_x="LMARGIN", new_y="NEXT")


def _draw_cover_page(pdf: _AuditPDF, doc_name: str) -> None:
    """Draw the full cover page on the current (first) page."""
    # Full-width dark bar at top
    pdf.set_fill_color(*_DARK)
    pdf.rect(0, 0, 210, 50, "F")
    # Purple accent stripe
    pdf.set_fill_color(*_PURPLE)
    pdf.rect(0, 46, 210, 4, "F")

    # ConfiDoc logo text
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(*_WHITE)
    pdf.set_xy(15, 12)
    pdf.cell(0, 12, "ConfiDoc")

    # Subtitle
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(*_GRAY)
    pdf.set_xy(15, 26)
    pdf.cell(0, 8, "Rapport de Conformite RGPD")

    # Document name box
    pdf.set_fill_color(240, 240, 255)
    pdf.set_draw_color(*_PURPLE)
    pdf.rect(15, 58, 180, 20, "FD")
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*_DARK)
    pdf.set_xy(20, 62)
    pdf.cell(0, 12, doc_name[:70])

    # Generation date
    pdf.set_xy(15, 86)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*_GRAY)
    now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y a %H:%M UTC")
    pdf.cell(0, 6, f"Genere le {now_str}")

    # Decorative divider
    pdf.set_draw_color(*_PURPLE)
    pdf.set_line_width(0.5)
    pdf.line(15, 100, 195, 100)
    pdf.set_line_width(0.2)

    # Summary block on cover
    pdf.set_xy(15, 108)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*_DARK)
    pdf.cell(0, 7, "Contenu du rapport :")
    pdf.set_xy(15, 118)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(60, 60, 80)
    items = [
        "-> Informations du document analyse",
        "-> Score de risque de reidentification",
        "-> Entites personnelles detectees et masquees",
        "-> Journal d'audit horodate (tracabilite RGPD)",
        "-> Declaration de conformite RGPD",
    ]
    for item in items:
        pdf.cell(0, 7, item, new_x="LMARGIN", new_y="NEXT")

    # Bottom bar with tagline
    pdf.set_fill_color(*_PURPLE)
    pdf.rect(0, 260, 210, 37, "F")
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*_WHITE)
    pdf.set_xy(15, 270)
    pdf.cell(0, 8, "Plateforme d'usage securise de l'IA sur documents sensibles")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(200, 196, 255)
    pdf.set_xy(15, 280)
    pdf.cell(0, 6, "confidoc.fr -- Protection RGPD par conception")


def generate_audit_pdf(
    document_info: dict[str, Any],
    risk_info: dict[str, Any] | None,
    entity_summary: dict[str, int],
    audit_entries: list[dict[str, Any]],
    anonymized_text_preview: str = "",
) -> bytes:
    """Generate a professional PDF audit report."""
    doc_name = document_info.get("filename", "Document")
    pdf = _AuditPDF(doc_name)
    pdf.alias_nb_pages()

    # --- Cover page ---
    pdf.add_page()
    _draw_cover_page(pdf, doc_name)

    # --- Content pages ---
    pdf.add_page()

    # -- Document Metadata --
    pdf.section_title("1. Informations du document")
    pdf.kv_row("Nom du fichier :", doc_name)
    pdf.kv_row("Identifiant :", document_info.get("document_id", "--"))
    pdf.kv_row("Date de creation :", document_info.get("created_at", "--"))
    pdf.kv_row("Type detecte :", document_info.get("doc_type", "Auto"))
    pdf.kv_row("Statut :", document_info.get("status", "--"))

    # -- Risk Score --
    pdf.section_title("2. Score de risque de reidentification")

    if risk_info:
        score = risk_info.get("score", 0)
        level = risk_info.get("level", "low")
        color = _RISK_COLORS.get(level, _GRAY)
        label = _RISK_LABELS.get(level, level.upper())

        pdf.ln(2)
        gauge_y = pdf.get_y()

        # Background track
        pdf.set_fill_color(230, 230, 244)
        pdf.rect(12, gauge_y, 150, 14, "F")

        # Filled portion
        fill_width = max(3, int(score * 150))
        pdf.set_fill_color(*color)
        pdf.rect(12, gauge_y, min(fill_width, 150), 14, "F")

        # Score badge on the right
        pdf.set_fill_color(*color)
        pdf.rect(170, gauge_y, 30, 14, "F")
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*_WHITE)
        pdf.set_xy(170, gauge_y + 1)
        pdf.cell(30, 12, f"{int(score * 100)}%", align="C")

        # Level label below gauge
        pdf.set_xy(12, gauge_y + 16)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*color)
        pdf.cell(0, 6, f"Niveau : {label}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        recommendation = risk_info.get("recommendation", "")
        if recommendation:
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(80, 80, 100)
            pdf.multi_cell(0, 5, recommendation)
            pdf.ln(2)

        pdf.kv_row("Validation humaine :", "Oui" if risk_info.get("human_validated") else "Non")
        if risk_info.get("validated_at"):
            pdf.kv_row("Date validation :", risk_info["validated_at"])
        if risk_info.get("expires_at"):
            pdf.kv_row("Expiration mapping :", risk_info["expires_at"])
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*_GRAY)
        pdf.cell(0, 6, "Aucune evaluation de risque disponible.", new_x="LMARGIN", new_y="NEXT")

    # -- Entity Summary --
    pdf.section_title("3. Entites detectees")

    if entity_summary:
        sorted_entities = sorted(entity_summary.items(), key=lambda x: -x[1])
        total = sum(v for _, v in sorted_entities)

        # Header row — purple, white text, no border
        pdf.set_fill_color(*_PURPLE)
        pdf.set_text_color(*_WHITE)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(90, 8, "  Type d'entite", fill=True, new_x="END")
        pdf.cell(40, 8, "Occurrences", fill=True, align="C", new_x="END")
        pdf.cell(40, 8, "Pourcentage", fill=True, align="C", new_x="LMARGIN", new_y="NEXT")

        # Data rows — no border, alternating backgrounds
        for i, (etype, count) in enumerate(sorted_entities):
            bg = (245, 244, 255) if i % 2 == 0 else _WHITE
            pdf.set_fill_color(*bg)
            pdf.set_text_color(30, 30, 50)
            pdf.set_font("Helvetica", "", 9)
            pdf.cell(90, 7, f"  {etype}", fill=True, new_x="END")
            pdf.cell(40, 7, str(count), fill=True, align="C", new_x="END")
            pct = f"{count / total * 100:.1f}%" if total else "--"
            pdf.cell(40, 7, pct, fill=True, align="C", new_x="LMARGIN", new_y="NEXT")

        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*_PURPLE)
        pdf.cell(0, 6, f"Total : {total} entites masquees", new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*_GRAY)
        pdf.cell(0, 6, "Aucune entite detectee.", new_x="LMARGIN", new_y="NEXT")

    # -- Audit Trail --
    pdf.section_title("4. Journal d'audit (tracabilite RGPD)")

    if audit_entries:
        # Header row
        pdf.set_fill_color(*_PURPLE)
        pdf.set_text_color(*_WHITE)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(35, 7, "  Date", fill=True, new_x="END")
        pdf.cell(47, 7, "Action", fill=True, new_x="END")
        pdf.cell(25, 7, "Methode", fill=True, align="C", new_x="END")
        pdf.cell(20, 7, "Code", fill=True, align="C", new_x="END")
        pdf.cell(53, 7, "Details", fill=True, new_x="LMARGIN", new_y="NEXT")

        for i, entry in enumerate(audit_entries[:50]):
            bg = (245, 244, 255) if i % 2 == 0 else _WHITE
            pdf.set_fill_color(*bg)
            pdf.set_text_color(30, 30, 50)
            pdf.set_font("Helvetica", "", 7)

            ts = entry.get("timestamp", "--")
            if ts and len(ts) > 19:
                ts = ts[:19].replace("T", " ")

            action = entry.get("action", "--")
            method = entry.get("method", "--")
            code = str(entry.get("status_code", "--"))

            details_dict = entry.get("details") or {}
            details_parts = []
            if isinstance(details_dict, dict):
                for k, v in list(details_dict.items())[:3]:
                    details_parts.append(f"{k}={v}")
            details = ", ".join(details_parts)[:40]

            pdf.cell(35, 5, f"  {(ts[:19] if ts else '--')}", fill=True, new_x="END")
            pdf.cell(47, 5, action[:28], fill=True, new_x="END")
            pdf.cell(25, 5, method, fill=True, align="C", new_x="END")
            pdf.cell(20, 5, code, fill=True, align="C", new_x="END")
            pdf.cell(53, 5, details, fill=True, new_x="LMARGIN", new_y="NEXT")

        if len(audit_entries) > 50:
            pdf.ln(2)
            pdf.set_font("Helvetica", "I", 7)
            pdf.set_text_color(*_GRAY)
            pdf.cell(
                0,
                5,
                f"... et {len(audit_entries) - 50} entrees supplementaires",
                new_x="LMARGIN",
                new_y="NEXT",
            )
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*_GRAY)
        pdf.cell(0, 6, "Aucune entree d'audit enregistree.", new_x="LMARGIN", new_y="NEXT")

    # -- Text Preview --
    if anonymized_text_preview:
        pdf.section_title("5. Apercu du texte anonymise")
        pdf.set_fill_color(248, 248, 252)
        pdf.set_font("Courier", "", 7)
        pdf.set_text_color(60, 60, 80)
        truncated = anonymized_text_preview[:3000]
        if len(anonymized_text_preview) > 3000:
            truncated += "\n\n[... texte tronque -- voir l'application pour le texte complet ...]"
        pdf.multi_cell(0, 4, truncated, fill=True)

    # -- RGPD Statement --
    pdf.add_page()
    pdf.section_title("Declaration de conformite RGPD")

    pdf.ln(2)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(40, 40, 60)
    intro = (
        "Ce rapport a ete genere par la plateforme ConfiDoc, concue selon les principes "
        "du RGPD et du privacy by design. ConfiDoc distingue pseudonymisation et "
        "anonymisation forte, mesure le risque residuel de reidentification, et "
        "journalise les traitements pour permettre un controle humain avant export."
    )
    pdf.multi_cell(0, 5, intro)

    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*_DARK)
    pdf.cell(0, 7, "Mecanismes mis en oeuvre :", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    mechanisms = [
        "-> Separation pseudonymisation / anonymisation forte",
        "-> Scoring du risque de reidentification (quasi-identifiants, combinaisons)",
        "-> Chiffrement des mappings reversibles (AES-128-CBC + HMAC-SHA256)",
        "-> Politique d'export conditionnee au niveau de risque",
        "-> Journal d'audit horodate et non modifiable",
        "-> Politique de retention et purge configurable",
        "-> Validation humaine obligatoire pour les exports a risque eleve",
    ]
    for mech in mechanisms:
        # Alternating light background for each item
        row_y = pdf.get_y()
        pdf.set_fill_color(248, 247, 255)
        pdf.rect(15, row_y, 175, 7, "F")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(40, 40, 70)
        pdf.set_xy(18, row_y)
        pdf.cell(0, 7, mech, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(8)
    # Notice box
    pdf.set_fill_color(255, 249, 230)
    pdf.set_draw_color(*_WARNING)
    notice_y = pdf.get_y()
    pdf.rect(15, notice_y, 175, 22, "FD")
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(120, 80, 0)
    pdf.set_xy(20, notice_y + 3)
    pdf.cell(0, 5, "Important :")
    pdf.set_font("Helvetica", "", 8)
    pdf.set_xy(20, notice_y + 10)
    pdf.multi_cell(
        165,
        4,
        "ConfiDoc aide a la conformite RGPD mais ne constitue pas un avis juridique. "
        "Une analyse de risque (AIPD) specifique peut etre necessaire selon le contexte.",
    )

    pdf.ln(12)
    # Signature line
    pdf.set_draw_color(*_PURPLE)
    pdf.set_line_width(0.4)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*_PURPLE)
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y a %H:%M UTC")
    pdf.cell(0, 6, f"Document genere le {now}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*_GRAY)
    pdf.cell(
        0,
        5,
        "ConfiDoc -- Plateforme d'usage securise de l'IA sur documents sensibles",
        new_x="LMARGIN",
        new_y="NEXT",
    )

    return pdf.output()
