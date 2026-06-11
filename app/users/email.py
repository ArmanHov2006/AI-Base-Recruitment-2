import email.mime.multipart
import email.mime.text

import aiosmtplib
import structlog

from app.config import settings

log = structlog.get_logger()


async def _send(to: str, subject: str, html: str) -> None:
    if not settings.smtp_host:
        log.info("email.stub", to=to, subject=subject)
        return

    msg = email.mime.multipart.MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg.attach(email.mime.text.MIMEText(html, "html"))

    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user or None,
        password=settings.smtp_password or None,
        start_tls=settings.smtp_use_tls,
    )


async def send_password_reset_email(email_addr: str, token: str) -> None:
    link = f"{settings.app_base_url}/reset-password?token={token}"
    await _send(
        to=email_addr,
        subject="Reset your password",
        html=f'<p>Click <a href="{link}">here</a> to reset your password. Link expires in 1 hour.</p>',
    )


async def send_invite_email(email_addr: str, token: str, role: str) -> None:
    link = f"{settings.app_base_url}/register?invite={token}"
    role_label = role.replace("_", " ").title()
    await _send(
        to=email_addr,
        subject="You've been invited to AI Recruitment",
        html=(
            f"<p>You've been invited as <strong>{role_label}</strong> to the "
            f"AI_Based_recruitment AI Recruitment platform.</p>"
            f'<p>Click <a href="{link}">here</a> to register. '
            f"Link expires in {settings.invite_token_expire_hours} hours.</p>"
        ),
    )
