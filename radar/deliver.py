import ssl
import smtplib
from email.message import EmailMessage

def _default_smtp_factory():
    return smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context())

def send_email(subject, html_body, settings, _smtp_factory=None) -> None:
    factory = _smtp_factory or _default_smtp_factory
    msg = EmailMessage()
    msg["From"] = settings.gmail_user
    msg["To"] = settings.email_recipient
    msg["Subject"] = subject
    msg.set_content("This email requires an HTML-capable client.")
    msg.add_alternative(html_body, subtype="html")
    with factory() as server:
        server.login(settings.gmail_user, settings.gmail_app_password)
        server.send_message(msg)
