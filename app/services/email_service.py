"""ConfiDoc Backend — Service email minimal (SMTP).

Utilisé pour l'envoi des liens de reset de mot de passe.
Si SMTP n'est pas configuré, l'email est loggé en clair (dev uniquement).
"""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

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
