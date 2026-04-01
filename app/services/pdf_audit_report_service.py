"""ConfiDoc — Professional RGPD audit report PDF generation.

Generates a branded, professional-grade PDF report with:
- ConfiDoc header with branding
- Document metadata
- Re-identification risk score with visual gauge
- Entity summary table
- Chronological audit trail
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
        self.set_fill_color(*_DARK)
        self.rect(0, 0, 210, 28, "F")

        self.set_font("Helvetica", "B", 16)
        self.set_text_color(*_WHITE)
        self.set_xy(12, 6)
        self.cell(0, 8, "ConfiDoc", new_x="LMARGIN")

        self.set_font("Helvetica", "", 9)
        self.set_text_color(*_GRAY)
        self.set_xy(12, 15)
        self.cell(0, 6, "Rapport d'audit RGPD", new_x="LMARGIN")

        self.set_font("Helvetica", "", 8)
        self.set_xy(140, 6)
        self.set_text_color(*_GRAY)
        now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
        self.cell(0, 8, f"Genere le {now}", align="R")

        self.set_xy(10, 32)

    def footer(self) -> None:
        self.set_y(-20)
        self.set_draw_color(*_PURPLE)
        self.line(10, self.get_y(), 200, self.get_y())
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(*_GRAY)
        self.cell(0, 10, f"ConfiDoc -- Rapport confidentiel -- Page {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title: str) -> None:
        self.ln(6)
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(*_PURPLE)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*_PURPLE)
        self.line(self.get_x(), self.get_y(), self.get_x() + 50, self.get_y())
        self.ln(4)

    def kv_row(self, key: str, value: str) -> None:
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(80, 80, 100)
        self.cell(55, 6, key, new_x="END")
        self.set_font("Helvetica", "", 9)
        self.set_text_color(30, 30, 50)
        self.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")


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
    pdf.add_page()

    # -- Document Metadata --
    pdf.section_title("1. Informations du document")
    pdf.kv_row("Nom du fichier", doc_name)
    pdf.kv_row("Identifiant", document_info.get("document_id", "--"))
    pdf.kv_row("Date de creation", document_info.get("created_at", "--"))
    pdf.kv_row("Type detecte", document_info.get("doc_type", "Auto"))
    pdf.kv_row("Statut", document_info.get("status", "--"))

    # -- Risk Score --
    pdf.section_title("2. Score de risque de reidentification")

    if risk_info:
        score = risk_info.get("score", 0)
        level = risk_info.get("level", "low")
        color = _RISK_COLORS.get(level, _GRAY)
        label = _RISK_LABELS.get(level, level.upper())

        gauge_y = pdf.get_y()
        pdf.set_fill_color(*_LIGHT_BG)
        pdf.rect(12, gauge_y, 140, 12, "F")

        fill_width = max(2, int(score * 100 * 1.4))
        pdf.set_fill_color(*color)
        pdf.rect(12, gauge_y, min(fill_width, 140), 12, "F")

        pdf.set_xy(155, gauge_y)
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(*color)
        pdf.cell(40, 12, f"{int(score * 100)}% -- {label}")

        pdf.set_xy(12, gauge_y + 16)

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(80, 80, 100)
        recommendation = risk_info.get("recommendation", "")
        if recommendation:
            pdf.multi_cell(0, 5, recommendation)
            pdf.ln(2)

        pdf.kv_row("Validation humaine", "Oui" if risk_info.get("human_validated") else "Non")
        if risk_info.get("validated_at"):
            pdf.kv_row("Date validation", risk_info["validated_at"])
        if risk_info.get("expires_at"):
            pdf.kv_row("Expiration mapping", risk_info["expires_at"])
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*_GRAY)
        pdf.cell(0, 6, "Aucune evaluation de risque disponible.", new_x="LMARGIN", new_y="NEXT")

    # -- Entity Summary --
    pdf.section_title("3. Entites detectees")

    if entity_summary:
        sorted_entities = sorted(entity_summary.items(), key=lambda x: -x[1])
        total = sum(v for _, v in sorted_entities)

        pdf.set_fill_color(*_PURPLE)
        pdf.set_text_color(*_WHITE)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(80, 7, "Type d'entite", border=1, fill=True, new_x="END")
        pdf.cell(35, 7, "Occurrences", border=1, fill=True, align="C", new_x="END")
        pdf.cell(35, 7, "% du total", border=1, fill=True, align="C", new_x="LMARGIN", new_y="NEXT")

        for i, (etype, count) in enumerate(sorted_entities):
            bg = _LIGHT_BG if i % 2 == 0 else _WHITE
            pdf.set_fill_color(*bg)
            pdf.set_text_color(30, 30, 50)
            pdf.set_font("Helvetica", "", 9)
            pdf.cell(80, 6, etype, border=1, fill=True, new_x="END")
            pdf.cell(35, 6, str(count), border=1, fill=True, align="C", new_x="END")
            pct = f"{count / total * 100:.1f}%" if total else "--"
            pdf.cell(35, 6, pct, border=1, fill=True, align="C", new_x="LMARGIN", new_y="NEXT")

        pdf.ln(2)
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
        pdf.set_fill_color(*_PURPLE)
        pdf.set_text_color(*_WHITE)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(35, 6, "Date", border=1, fill=True, new_x="END")
        pdf.cell(45, 6, "Action", border=1, fill=True, new_x="END")
        pdf.cell(25, 6, "Methode", border=1, fill=True, align="C", new_x="END")
        pdf.cell(20, 6, "Code", border=1, fill=True, align="C", new_x="END")
        pdf.cell(55, 6, "Details", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")

        for i, entry in enumerate(audit_entries[:50]):
            bg = _LIGHT_BG if i % 2 == 0 else _WHITE
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

            pdf.cell(35, 5, ts[:19] if ts else "--", border=1, fill=True, new_x="END")
            pdf.cell(45, 5, action[:25], border=1, fill=True, new_x="END")
            pdf.cell(25, 5, method, border=1, fill=True, align="C", new_x="END")
            pdf.cell(20, 5, code, border=1, fill=True, align="C", new_x="END")
            pdf.cell(55, 5, details, border=1, fill=True, new_x="LMARGIN", new_y="NEXT")

        if len(audit_entries) > 50:
            pdf.set_font("Helvetica", "I", 7)
            pdf.set_text_color(*_GRAY)
            pdf.cell(0, 5, f"... et {len(audit_entries) - 50} entrees supplementaires", new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*_GRAY)
        pdf.cell(0, 6, "Aucune entree d'audit enregistree.", new_x="LMARGIN", new_y="NEXT")

    # -- Text Preview --
    if anonymized_text_preview:
        pdf.section_title("5. Apercu du texte anonymise")
        pdf.set_font("Courier", "", 7)
        pdf.set_text_color(60, 60, 80)
        truncated = anonymized_text_preview[:3000]
        if len(anonymized_text_preview) > 3000:
            truncated += "\n\n[... texte tronque -- voir l'application pour le texte complet ...]"
        pdf.multi_cell(0, 4, truncated)

    # -- RGPD Statement --
    pdf.add_page()
    pdf.section_title("Declaration de conformite RGPD")

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(40, 40, 60)
    statement = (
        "Ce rapport a ete genere par la plateforme ConfiDoc, concue selon les principes "
        "du RGPD et du privacy by design.\n\n"
        "ConfiDoc distingue pseudonymisation et anonymisation forte, mesure le risque "
        "residuel de reidentification, et journalise les traitements pour permettre un "
        "controle humain avant export.\n\n"
        "Les mecanismes mis en oeuvre incluent :\n"
        "  - Separation pseudonymisation / anonymisation forte\n"
        "  - Scoring du risque de reidentification (quasi-identifiants, combinaisons)\n"
        "  - Chiffrement des mappings reversibles (AES-128-CBC + HMAC-SHA256)\n"
        "  - Politique d'export conditionnee au niveau de risque\n"
        "  - Journal d'audit horodate et non modifiable\n"
        "  - Politique de retention et purge configurable\n"
        "  - Validation humaine obligatoire pour les exports a risque eleve\n\n"
        "Important : ConfiDoc aide a la conformite RGPD mais ne constitue pas un "
        "avis juridique. Une analyse de risque (AIPD) specifique peut etre necessaire "
        "selon le contexte de traitement."
    )
    pdf.multi_cell(0, 5, statement)

    pdf.ln(10)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*_PURPLE)
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y a %H:%M UTC")
    pdf.cell(0, 6, f"Document genere le {now}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*_GRAY)
    pdf.cell(0, 5, "ConfiDoc -- Plateforme d'usage securise de l'IA sur documents sensibles", new_x="LMARGIN", new_y="NEXT")

    return pdf.output()
