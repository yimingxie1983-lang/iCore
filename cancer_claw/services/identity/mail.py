from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from cancer_claw.config import settings


class MailError(Exception):
    pass


def is_mail_configured() -> bool:

    return bool(settings.mail.host and settings.mail.from_addr)


async def send_email_async(to: str, subject: str, text: str) -> None:

    await asyncio.to_thread(_send, to, subject, text)


def _send(to: str, subject: str, text: str) -> None:

    if not is_mail_configured():
        raise MailError("邮件服务未配置")
    msg = EmailMessage()
    msg["From"] = settings.mail.from_addr
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    with smtplib.SMTP(
        settings.mail.host, settings.mail.port, timeout=settings.mail.timeout
    ) as smtp:
        if settings.mail.starttls:
            smtp.starttls()
        if settings.mail.username:
            smtp.login(settings.mail.username, settings.mail.password)
        smtp.send_message(msg)
