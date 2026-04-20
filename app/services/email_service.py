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

        logger.info("password_reset_email_sent", to=to_email)
        return True

    except Exception as exc:
        logger.warning("password_reset_email_failed", to=to_email, error=str(exc))
        return False


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

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM
        msg["To"] = recipient
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        if settings.SMTP_TLS:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
                server.ehlo()
                server.starttls()
                if settings.SMTP_USER:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.SMTP_FROM, [recipient], msg.as_string())
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
                if settings.SMTP_USER:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.SMTP_FROM, [recipient], msg.as_string())

        logger.info("beta_lead_notification_sent", recipient=recipient, source=source)
        return True
    except Exception as exc:
        logger.warning("beta_lead_notification_failed", error=str(exc), source=source)
        return False
