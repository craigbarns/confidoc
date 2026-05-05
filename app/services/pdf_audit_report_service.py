"""ConfiDoc — Professional RGPD audit report PDF generation.

Generates a branded, premium-grade PDF report with:
- ConfiDoc dark cover page with stats cards and purple accents
- Document metadata
- Re-identification risk score with visual gauge + badge
- Entity summary table (borderless, alternating rows)
- Chronological audit trail
- RGPD compliance statement
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fpdf import FPDF


_PURPLE = (124, 116, 255)
_DARK = (15, 17, 23)
_WHITE = (255, 255, 255)
_GRAY = (163, 171, 199)
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


def _fmt_date(raw: str | None) -> str:
    """Parse ISO date string to human-readable display format."""
    if not raw or raw == "--":
        return "--"
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y a %H:%M UTC")
    except (ValueError, AttributeError, TypeError):
        return str(raw)[:19]


class _AuditPDF(FPDF):
    def __init__(self, doc_name: str) -> None:
        super().__init__()
        self._doc_name = doc_name
        self.set_auto_page_break(auto=True, margin=25)

    def header(self) -> None:
        if self.page_no() == 1:
            return
        # Dark top bar
        self.set_fill_color(*_DARK)
        self.rect(0, 0, 210, 22, "F")
        # Purple accent stripe
        self.set_fill_color(*_PURPLE)
        self.rect(0, 20, 210, 2, "F")
        # Logo
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(*_WHITE)
        self.set_xy(12, 5)
        self.cell(0, 7, "ConfiDoc", new_x="LMARGIN")
        # Subtitle
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*_GRAY)
        self.set_xy(12, 13)
        self.cell(0, 5, "Rapport de Conformite RGPD", new_x="LMARGIN")
        # Date right-aligned
        self.set_font("Helvetica", "", 8)
        self.set_xy(120, 7)
        self.set_text_color(*_GRAY)
        now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
        self.cell(80, 6, f"Genere le {now}", align="R")
        self.set_xy(15, 30)

    def footer(self) -> None:
        if self.page_no() == 1:
            return
        self.set_y(-18)
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
        self.set_x(12)
        self.cell(60, 7, key, new_x="END")
        self.set_font("Helvetica", "", 9)
        self.set_text_color(30, 30, 50)
        self.cell(0, 7, value, new_x="LMARGIN", new_y="NEXT")


def _draw_stat_card(
    pdf: _AuditPDF,
    x: float,
    y: float,
    w: float,
    h: float,
    value: str,
    label: str,
    accent: tuple[int, int, int],
) -> None:
    """Draw a stat card on the cover page."""
    pdf.set_fill_color(20, 20, 38)
    pdf.set_draw_color(*accent)
    pdf.set_line_width(0.5)
    pdf.rect(x, y, w, h, "FD")
    pdf.set_line_width(0.2)
    # Top accent bar
    pdf.set_fill_color(*accent)
    pdf.rect(x, y, w, 3, "F")
    # Value (large)
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(*_WHITE)
    pdf.set_xy(x, y + 6)
    pdf.cell(w, 8, value, align="C")
    # Label (small)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(*_GRAY)
    pdf.set_xy(x, y + 16)
    pdf.cell(w, 5, label, align="C")


def _draw_cover_page(
    pdf: _AuditPDF,
    doc_name: str,
    entity_count: int = 0,
    risk_level: str = "low",
    page_count: int = 0,
) -> None:
    """Draw the cover page. Auto page break is disabled to prevent spillover."""
    # Disable auto page break — cover uses absolute positioning past the 272mm threshold
    pdf.set_auto_page_break(False)

    # Dark header bar
    pdf.set_fill_color(*_DARK)
    pdf.rect(0, 0, 210, 52, "F")
    # Purple accent stripe
    pdf.set_fill_color(*_PURPLE)
    pdf.rect(0, 48, 210, 4, "F")

    # ConfiDoc logo
    pdf.set_font("Helvetica", "B", 30)
    pdf.set_text_color(*_WHITE)
    pdf.set_xy(15, 10)
    pdf.cell(0, 14, "ConfiDoc")
    # Tagline under logo
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(*_GRAY)
    pdf.set_xy(15, 28)
    pdf.cell(0, 8, "Rapport de Conformite RGPD")

    # Document name box
    pdf.set_fill_color(18, 20, 38)
    pdf.set_draw_color(*_PURPLE)
    pdf.set_line_width(0.8)
    pdf.rect(15, 62, 180, 18, "FD")
    pdf.set_line_width(0.2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*_WHITE)
    pdf.set_xy(21, 66)
    pdf.cell(0, 10, doc_name[:72])

    # Generation date
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*_GRAY)
    pdf.set_xy(15, 86)
    now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y a %H:%M UTC")
    pdf.cell(0, 6, f"Genere le {now_str}")

    # Divider
    pdf.set_draw_color(50, 52, 80)
    pdf.set_line_width(0.4)
    pdf.line(15, 97, 195, 97)
    pdf.set_line_width(0.2)

    # ---- Stats row (3 cards) ----
    risk_color = _RISK_COLORS.get(risk_level, _GRAY)
    risk_label_text = _RISK_LABELS.get(risk_level, risk_level.upper())
    card_w = 54.0
    card_h = 28.0
    card_y = 103.0
    gap = 7.5
    _draw_stat_card(pdf, 15, card_y, card_w, card_h, str(entity_count), "entites masquees", _PURPLE)
    _draw_stat_card(pdf, 15 + card_w + gap, card_y, card_w, card_h, risk_label_text, "niveau de risque", risk_color)
    pages_val = str(page_count) if page_count else "--"
    _draw_stat_card(pdf, 15 + 2 * (card_w + gap), card_y, card_w, card_h, pages_val, "pages analysees", (100, 120, 200))

    # ---- Content summary ----
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(100, 100, 140)
    pdf.set_xy(15, 143)
    pdf.cell(0, 6, "CONTENU DU RAPPORT")

    pdf.set_draw_color(45, 45, 70)
    pdf.set_line_width(0.3)
    pdf.line(15, 151, 195, 151)
    pdf.set_line_width(0.2)

    items = [
        "Informations du document analyse",
        "Score de risque de reidentification",
        "Trust Score et AI Readiness",
        "Entites personnelles detectees et masquees",
        "Journal d'audit horodate (tracabilite RGPD)",
        "Recommandation DPO et statut d'export",
        "Declaration de conformite RGPD",
    ]
    y_item = 155.0
    for item in items:
        # Purple square bullet
        pdf.set_fill_color(*_PURPLE)
        pdf.rect(17.5, y_item + 2, 2, 2, "F")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(180, 180, 210)
        pdf.set_xy(23, y_item)
        pdf.cell(0, 6, item)
        y_item += 8.0

    # ---- Purple bottom bar ----
    pdf.set_fill_color(90, 84, 200)
    pdf.rect(0, 248, 210, 6, "F")
    pdf.set_fill_color(*_PURPLE)
    pdf.rect(0, 254, 210, 43, "F")

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*_WHITE)
    pdf.set_xy(15, 262)
    pdf.cell(0, 8, "Plateforme d'usage securise de l'IA sur documents sensibles")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(200, 196, 255)
    pdf.set_xy(15, 272)
    pdf.cell(0, 6, "confidoc.fr  --  Protection RGPD par conception")

    # Re-enable auto page break for subsequent content pages
    pdf.set_auto_page_break(True, margin=25)


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
    entity_count = sum(entity_summary.values()) if entity_summary else 0
    risk_level = str(risk_info.get("level", "low") if risk_info else "low")
    page_count = int(document_info.get("pages") or 0)
    _draw_cover_page(pdf, doc_name, entity_count, risk_level, page_count)

    # --- Content pages ---
    pdf.add_page()

    # 1. Document metadata
    pdf.section_title("1. Informations du document")
    pdf.kv_row("Nom du fichier :", doc_name)
    pdf.kv_row("Identifiant :", str(document_info.get("document_id") or "--"))
    pdf.kv_row("Date de creation :", _fmt_date(str(document_info.get("created_at") or "--")))
    pdf.kv_row("Type detecte :", str(document_info.get("doc_type") or "Auto"))
    pdf.kv_row("Statut :", str(document_info.get("status") or "--"))

    # 2. Risk score
    pdf.section_title("2. Score de risque de reidentification")

    if risk_info:
        score_raw = float(risk_info.get("score") or 0)
        score = score_raw / 100 if score_raw > 1 else score_raw
        level = str(risk_info.get("level") or "low")
        color = _RISK_COLORS.get(level, _GRAY)
        label = _RISK_LABELS.get(level, level.upper())

        pdf.ln(2)
        gauge_y = pdf.get_y()

        # Track background
        pdf.set_fill_color(225, 225, 242)
        pdf.rect(12, gauge_y, 150, 14, "F")
        # Filled portion
        fill_w = max(3, int(score * 150))
        pdf.set_fill_color(*color)
        pdf.rect(12, gauge_y, min(fill_w, 150), 14, "F")
        # Score badge
        pdf.set_fill_color(*color)
        pdf.rect(170, gauge_y, 30, 14, "F")
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*_WHITE)
        pdf.set_xy(170, gauge_y + 1)
        pdf.cell(30, 12, f"{int(score * 100)}%", align="C")
        # Level label
        pdf.set_xy(12, gauge_y + 16)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*color)
        pdf.cell(0, 6, f"Niveau : {label}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        recommendation = str(risk_info.get("recommendation") or "")
        if recommendation:
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(80, 80, 100)
            pdf.multi_cell(0, 5, recommendation)
            pdf.ln(2)

        validation_label = "Oui" if risk_info.get("human_validated") else "Non - revue recommandee"
        pdf.kv_row("Validation humaine :", validation_label)
        if risk_info.get("validated_at"):
            pdf.kv_row("Date validation :", _fmt_date(str(risk_info["validated_at"])))
        if risk_info.get("expires_at"):
            pdf.kv_row("Expiration mapping :", _fmt_date(str(risk_info["expires_at"])))
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*_GRAY)
        pdf.cell(0, 6, "Aucune evaluation de risque disponible.", new_x="LMARGIN", new_y="NEXT")

    # 2b. Trust / AI readiness
    trust_info = document_info.get("trust")
    if isinstance(trust_info, dict):
        pdf.section_title("2b. Trust Score et AI Readiness")
        pdf.kv_row("Trust Score :", f"{trust_info.get('trust_score', '--')}/100")
        pdf.kv_row("AI Readiness :", f"{trust_info.get('ai_readiness_score', '--')}/100")
        pdf.kv_row("Niveau readiness :", str(trust_info.get("ai_readiness_level") or "--"))
        export_label = str(document_info.get("export_policy") or "--")
        pdf.kv_row("Statut export :", export_label)
        dpo = str(
            document_info.get("dpo_recommendation")
            or "Revue DPO recommandee avant diffusion externe si le risque n'est pas faible."
        )
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(80, 80, 100)
        pdf.multi_cell(0, 5, dpo)

    # 3. Entity summary
    pdf.section_title("3. Entites detectees")

    if entity_summary:
        sorted_entities = sorted(entity_summary.items(), key=lambda x: -x[1])
        total = sum(v for _, v in sorted_entities)

        # Header row
        pdf.set_fill_color(*_PURPLE)
        pdf.set_text_color(*_WHITE)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_x(12)
        pdf.cell(82, 8, "  Type d'entite", fill=True, new_x="END")
        pdf.cell(36, 8, "Occurrences", fill=True, align="C", new_x="END")
        pdf.cell(36, 8, "Pourcentage", fill=True, align="C", new_x="LMARGIN", new_y="NEXT")

        for i, (etype, count) in enumerate(sorted_entities):
            bg = (245, 244, 255) if i % 2 == 0 else _WHITE
            pdf.set_fill_color(*bg)
            pdf.set_text_color(30, 30, 50)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_x(12)
            pdf.cell(82, 7, f"  {etype}", fill=True, new_x="END")
            pdf.cell(36, 7, str(count), fill=True, align="C", new_x="END")
            pct = f"{count / total * 100:.1f}%" if total else "--"
            pdf.cell(36, 7, pct, fill=True, align="C", new_x="LMARGIN", new_y="NEXT")

        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*_PURPLE)
        pdf.set_x(12)
        pdf.cell(0, 6, f"Total : {total} entites masquees", new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*_GRAY)
        pdf.cell(0, 6, "Aucune entite detectee.", new_x="LMARGIN", new_y="NEXT")

    # 4. Audit trail
    pdf.section_title("4. Journal d'audit (tracabilite RGPD)")

    if audit_entries:
        # Header
        pdf.set_fill_color(*_PURPLE)
        pdf.set_text_color(*_WHITE)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_x(12)
        pdf.cell(36, 7, "  Date", fill=True, new_x="END")
        pdf.cell(46, 7, "Action", fill=True, new_x="END")
        pdf.cell(22, 7, "Methode", fill=True, align="C", new_x="END")
        pdf.cell(18, 7, "Code", fill=True, align="C", new_x="END")
        pdf.cell(50, 7, "Details", fill=True, new_x="LMARGIN", new_y="NEXT")

        for i, entry in enumerate(audit_entries[:50]):
            bg = (245, 244, 255) if i % 2 == 0 else _WHITE
            pdf.set_fill_color(*bg)
            pdf.set_text_color(30, 30, 50)
            pdf.set_font("Helvetica", "", 7)

            ts = str(entry.get("timestamp") or "--")
            if len(ts) > 19:
                ts = ts[:19].replace("T", " ")

            action = str(entry.get("action") or "--")
            method = str(entry.get("method") or "--")
            code = str(entry.get("status_code") or "--")

            details_dict = entry.get("details") or {}
            details_parts: list[str] = []
            if isinstance(details_dict, dict):
                for k, v in list(details_dict.items())[:3]:
                    details_parts.append(f"{k}={v}")
            details = ", ".join(details_parts)[:42]

            pdf.set_x(12)
            pdf.cell(36, 5, f"  {ts[:19]}", fill=True, new_x="END")
            pdf.cell(46, 5, action[:28], fill=True, new_x="END")
            pdf.cell(22, 5, method, fill=True, align="C", new_x="END")
            pdf.cell(18, 5, code, fill=True, align="C", new_x="END")
            pdf.cell(50, 5, details, fill=True, new_x="LMARGIN", new_y="NEXT")

        if len(audit_entries) > 50:
            pdf.ln(2)
            pdf.set_font("Helvetica", "I", 7)
            pdf.set_text_color(*_GRAY)
            pdf.cell(
                0, 5,
                f"... et {len(audit_entries) - 50} entrees supplementaires",
                new_x="LMARGIN",
                new_y="NEXT",
            )
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*_GRAY)
        pdf.cell(0, 6, "Aucune entree d'audit enregistree.", new_x="LMARGIN", new_y="NEXT")

    # 5. Anonymized text preview
    if anonymized_text_preview:
        pdf.section_title("5. Apercu du texte anonymise")
        pdf.set_fill_color(248, 248, 252)
        pdf.set_font("Courier", "", 7)
        pdf.set_text_color(60, 60, 80)
        truncated = anonymized_text_preview[:3000]
        if len(anonymized_text_preview) > 3000:
            truncated += "\n\n[... texte tronque -- voir l'application pour le texte complet ...]"
        pdf.multi_cell(0, 4, truncated, fill=True)

    # 6. RGPD compliance statement
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
        "Separation pseudonymisation / anonymisation forte",
        "Scoring du risque de reidentification (quasi-identifiants, combinaisons)",
        "Chiffrement des mappings reversibles (AES-128-CBC + HMAC-SHA256)",
        "Politique d'export conditionnee au niveau de risque",
        "Journal d'audit horodate et non modifiable",
        "Politique de retention et purge configurable",
        "Validation humaine obligatoire pour les exports a risque eleve",
    ]
    for i, mech in enumerate(mechanisms):
        row_y = pdf.get_y()
        bg = (245, 244, 255) if i % 2 == 0 else (250, 250, 255)
        pdf.set_fill_color(*bg)
        pdf.rect(15, row_y, 175, 7, "F")
        # Purple square bullet
        pdf.set_fill_color(*_PURPLE)
        pdf.rect(18, row_y + 2.5, 2, 2, "F")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(40, 40, 70)
        pdf.set_xy(23, row_y)
        pdf.cell(0, 7, mech, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(8)
    # Notice / disclaimer box
    pdf.set_fill_color(255, 249, 230)
    pdf.set_draw_color(*_WARNING)
    pdf.set_line_width(0.5)
    notice_y = pdf.get_y()
    pdf.rect(15, notice_y, 175, 22, "FD")
    pdf.set_line_width(0.2)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(120, 80, 0)
    pdf.set_xy(20, notice_y + 3)
    pdf.cell(0, 5, "Important :")
    pdf.set_font("Helvetica", "", 8)
    pdf.set_xy(20, notice_y + 10)
    pdf.multi_cell(
        165, 4,
        "Score d'aide a la decision, ne remplace pas une validation juridique/DPO. "
        "ConfiDoc aide a la conformite RGPD mais ne constitue pas un avis juridique. "
        "Une analyse de risque (AIPD) specifique peut etre necessaire selon le contexte.",
    )

    pdf.ln(12)
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
        0, 5,
        "ConfiDoc -- Plateforme d'usage securise de l'IA sur documents sensibles",
        new_x="LMARGIN",
        new_y="NEXT",
    )

    return pdf.output()
