import smtplib
import ssl
from email.message import EmailMessage

from app.core.email_config import get_email_settings


def send_email(recipient: str, subject: str, body: str):
    settings = get_email_settings()
    message = EmailMessage()
    message["From"] = str(settings.mail_from)
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    tls_context = ssl.create_default_context()
    if settings.smtp_security == "ssl":
        connection = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port,
            timeout=settings.smtp_timeout_seconds, context=tls_context,
        )
    else:
        connection = smtplib.SMTP(
            settings.smtp_host, settings.smtp_port,
            timeout=settings.smtp_timeout_seconds,
        )
    with connection as smtp:
        if settings.smtp_security == "starttls":
            smtp.starttls(context=tls_context)
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
