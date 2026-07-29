"""Send-only Gmail API wrapper. Scoped to gmail.send only — never inbox/read access.

Requires GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN, GMAIL_SENDER_EMAIL
in the environment (see get_gmail_token.py for the one-time setup that produces the
refresh token, and dues_automation/README.md for the full Google Cloud walkthrough).
"""
import base64
from email.message import EmailMessage

from dues_automation import config

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


class GmailNotConfigured(RuntimeError):
    pass


def _build_service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    if not all([config.GMAIL_CLIENT_ID, config.GMAIL_CLIENT_SECRET, config.GMAIL_REFRESH_TOKEN, config.GMAIL_SENDER_EMAIL]):
        raise GmailNotConfigured(
            "Gmail credentials are not set. Run get_gmail_token.py and populate "
            "GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET / GMAIL_REFRESH_TOKEN / GMAIL_SENDER_EMAIL in .env"
        )

    creds = Credentials(
        token=None,
        refresh_token=config.GMAIL_REFRESH_TOKEN,
        client_id=config.GMAIL_CLIENT_ID,
        client_secret=config.GMAIL_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    return build("gmail", "v1", credentials=creds)


def send_email(to_email: str, subject: str, body: str) -> dict:
    """Send a plain-text email via the Gmail API. Raises on any failure —
    callers (send_emails.py) are responsible for try/except + logging."""
    service = _build_service()

    message = EmailMessage()
    message.set_content(body)
    message["To"] = to_email
    message["From"] = config.GMAIL_SENDER_EMAIL
    message["Subject"] = subject

    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return service.users().messages().send(userId="me", body={"raw": encoded}).execute()
