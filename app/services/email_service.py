"""ConfiDoc Backend — Service email minimal (SMTP).

Utilisé pour l'envoi des liens de reset de mot de passe.
Si SMTP n'est pas configuré, l'email est loggé en clair (dev uniquement).
"""

from __future__ import annotations

import html
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _send_smtp_email(
    *,
    subject: str,
    to_email: str,
    text_body: str,
    html_body: str,
) -> bool:
    """Send a multipart email via the configured SMTP server."""
    settings = get_settings()

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to_email
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        if settings.SMTP_TLS:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
                server.ehlo()
                server.starttls()
                if settings.SMTP_USER:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.SMTP_FROM, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
                if settings.SMTP_USER:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.SMTP_FROM, [to_email], msg.as_string())
        return True
    except Exception as exc:
        logger.warning("smtp_email_failed", to=to_email, error=str(exc), subject=subject)
        return False


async def send_password_reset_email(to_email: str, reset_url: str) -> bool:
    """Envoie le lien de reset de mot de passe par email.

    Retourne True si envoyé, False si échec (l'appelant doit rester silencieux
    pour éviter l'énumération d'emails).
    """
    settings = get_settings()

    subject = "Réinitialisation de votre mot de passe ConfiDoc"
    html_body = f"""
    <html><body>
    <p>Bonjour,</p>
    <p>Vous avez demandé la réinitialisation de votre mot de passe ConfiDoc.</p>
    <p>
      <a href="{reset_url}" style="
        background:#2563eb;color:white;padding:10px 20px;
        border-radius:6px;text-decoration:none;display:inline-block;">
        Réinitialiser mon mot de passe
      </a>
    </p>
    <p>Ce lien est valable {settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes.</p>
    <p>Si vous n'avez pas fait cette demande, ignorez cet email.</p>
    <hr/>
    <p style="font-size:12px;color:#6b7280;">
      ConfiDoc — Confidentialité documentaire pour professions réglementées
    </p>
    </body></html>
    """
    text_body = (
        f"Réinitialisation de votre mot de passe ConfiDoc.\n\n"
        f"Lien (valable {settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes) :\n{reset_url}\n\n"
        f"Si vous n'avez pas fait cette demande, ignorez cet email."
    )

    if not settings.SMTP_HOST:
        # Dev mode : log le lien (jamais en production)
        if not settings.is_production:
            logger.info(
                "password_reset_email_dev_mode",
                to=to_email,
                reset_url=reset_url,
                note="Configure SMTP_HOST to send real emails",
            )
            return True
        logger.warning("password_reset_email_skipped_no_smtp", to=to_email)
        return False

    sent = _send_smtp_email(
        subject=subject,
        to_email=to_email,
        text_body=text_body,
        html_body=html_body,
    )
    if sent:
        logger.info("password_reset_email_sent", to=to_email)
    return sent


async def send_beta_lead_notification(lead: dict[str, Any]) -> bool:
    """Notify the team about a new public beta access request."""
    settings = get_settings()
    recipient = settings.BETA_LEAD_RECIPIENT_EMAIL or settings.SMTP_FROM

    email = str(lead.get("email", "")).strip()
    company = str(lead.get("company", "")).strip()
    full_name = str(lead.get("full_name", "")).strip()
    role = str(lead.get("role") or "").strip()
    team_size = str(lead.get("team_size") or "").strip()
    volume = str(lead.get("document_volume") or "").strip()
    use_case = str(lead.get("use_case", "")).strip()
    source = str(lead.get("source") or "landing").strip()

    subject = f"Nouveau lead beta ConfiDoc — {company or email}"
    text_body = (
        "Nouveau lead beta ConfiDoc\n\n"
        f"Nom: {full_name}\n"
        f"Email: {email}\n"
        f"Cabinet / societe: {company}\n"
        f"Role: {role or '-'}\n"
        f"Taille equipe: {team_size or '-'}\n"
        f"Volume documents: {volume or '-'}\n"
        f"Source: {source}\n\n"
        f"Cas d'usage:\n{use_case}\n"
    )
    html_body = f"""
    <html><body>
      <h2>Nouveau lead beta ConfiDoc</h2>
      <table cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
        <tr><td><strong>Nom</strong></td><td>{html.escape(full_name)}</td></tr>
        <tr><td><strong>Email</strong></td><td>{html.escape(email)}</td></tr>
        <tr><td><strong>Cabinet / societe</strong></td><td>{html.escape(company)}</td></tr>
        <tr><td><strong>Role</strong></td><td>{html.escape(role or "-")}</td></tr>
        <tr><td><strong>Taille equipe</strong></td><td>{html.escape(team_size or "-")}</td></tr>
        <tr><td><strong>Volume documents</strong></td><td>{html.escape(volume or "-")}</td></tr>
        <tr><td><strong>Source</strong></td><td>{html.escape(source)}</td></tr>
      </table>
      <h3>Cas d'usage</h3>
      <p>{html.escape(use_case).replace(chr(10), "<br>")}</p>
    </body></html>
    """

    if not settings.SMTP_HOST:
        logger.info(
            "beta_lead_notification_skipped_no_smtp",
            email_domain=email.split("@")[-1] if "@" in email else "",
            company=company,
            source=source,
        )
        return False

    sent = _send_smtp_email(
        subject=subject,
        to_email=recipient,
        text_body=text_body,
        html_body=html_body,
    )
    if sent:
        logger.info("beta_lead_notification_sent", recipient=recipient, source=source)
    return sent


async def send_beta_welcome_email(lead: dict[str, Any]) -> bool:
    """Send an acknowledgement email to a beta applicant."""
    settings = get_settings()

    email = str(lead.get("email", "")).strip()
    if not email:
        return False

    full_name = str(lead.get("full_name", "")).strip()
    company = str(lead.get("company", "")).strip()
    use_case = str(lead.get("use_case", "")).strip()
    first_name = full_name.split()[0] if full_name else "Bonjour"
    trust_center_url = f"{settings.APP_BASE_URL.rstrip('/')}/trust"
    demo_url = f"{settings.APP_BASE_URL.rstrip('/')}/#demo-section"

    subject = "ConfiDoc — votre demande beta a bien ete recue"
    text_body = (
        f"{first_name},\n\n"
        "Votre demande d'acces beta ConfiDoc a bien ete recue.\n\n"
        f"Structure: {company or '-'}\n"
        f"Cas d'usage: {use_case or '-'}\n\n"
        "Suite du process:\n"
        "- qualification du cas d'usage et du volume documentaire\n"
        "- priorisation des pilotes a fort enjeu RGPD\n"
        "- retour de notre equipe avec la prochaine etape\n\n"
        f"Demo publique: {demo_url}\n"
        f"Trust Center: {trust_center_url}\n"
    )
    html_body = f"""
    <html><body>
      <p>{html.escape(first_name)},</p>
      <p>Votre demande d'acces beta <strong>ConfiDoc</strong> a bien ete recue.</p>
      <table cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
        <tr><td><strong>Structure</strong></td><td>{html.escape(company or "-")}</td></tr>
        <tr><td><strong>Cas d'usage</strong></td><td>{html.escape(use_case or "-")}</td></tr>
      </table>
      <p>Suite du process:</p>
      <ul>
        <li>qualification du cas d'usage et du volume documentaire</li>
        <li>priorisation des pilotes a fort enjeu RGPD</li>
        <li>retour de notre equipe avec la prochaine etape</li>
      </ul>
      <p>
        <a href="{html.escape(demo_url)}" style="
          background:#6c5ce7;color:white;padding:10px 18px;
          border-radius:6px;text-decoration:none;display:inline-block;margin-right:8px;">
          Voir la demo publique
        </a>
        <a href="{html.escape(trust_center_url)}" style="
          background:#0f172a;color:white;padding:10px 18px;
          border-radius:6px;text-decoration:none;display:inline-block;">
          Ouvrir le Trust Center
        </a>
      </p>
      <hr/>
      <p style="font-size:12px;color:#6b7280;">
        ConfiDoc — IA documentaire RGPD pour cabinets et professions reglementees
      </p>
    </body></html>
    """

    if not settings.SMTP_HOST:
        logger.info(
            "beta_welcome_email_skipped_no_smtp",
            email_domain=email.split("@")[-1] if "@" in email else "",
            company=company,
        )
        return False

    sent = _send_smtp_email(
        subject=subject,
        to_email=email,
        text_body=text_body,
        html_body=html_body,
    )
    if sent:
        logger.info(
            "beta_welcome_email_sent", email_domain=email.split("@")[-1] if "@" in email else ""
        )
    return sent
