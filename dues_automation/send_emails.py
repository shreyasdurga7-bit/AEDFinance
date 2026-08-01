"""Section 5.6 — donation thank-yous, dues confirmations, and dues reminders.

Every email is drafted by Gemini, then gated by SEND_MODE:
  - "review" (default): written to a local draft file + logged, nothing sent.
  - "live": sent via Gmail (send-only OAuth scope), then logged.
A blank member email always falls back to a local draft, even in live mode —
this must never fail silently and must never invent a recipient.
"""
import sqlite3
from datetime import datetime, timedelta

from google import genai
from google.genai import types as genai_types

from dues_automation import config, gmail_client
from dues_automation.parse import extract_json

DRAFT_SYSTEM_PROMPT = """You draft short emails on behalf of the Treasurer Committee of Alpha \
Epsilon Delta (AED), a college organization. Return ONLY valid JSON with exactly two keys: \
"subject" and "body". No markdown, no prose outside the JSON. Keep the body under 150 words, \
warm and professional, and sign off as "AED Treasurer Committee"."""


def _draft(client: genai.Client | None, user_prompt: str, fallback: tuple[str, str]) -> tuple[str, str]:
    if client is None:
        return fallback
    try:
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=user_prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=DRAFT_SYSTEM_PROMPT,
                max_output_tokens=400,
            ),
        )
        parsed = extract_json(response.text)
        return parsed["subject"], parsed["body"]
    except Exception:  # noqa: BLE001 — a bad draft must never halt the batch
        return fallback


def draft_donation_thanks(client: genai.Client | None, member: dict, amount: float) -> tuple[str, str]:
    fallback = (
        "Thank you for your donation to AED",
        f"Hi {member['full_name']},\n\nThank you for your generous donation of ${amount:,.2f} to AED. "
        "We really appreciate your support.\n\nAED Treasurer Committee",
    )
    prompt = (
        f"Draft a thank-you email to {member['full_name']} for their ${amount:,.2f} donation to AED. "
        "Reference the specific amount given."
    )
    return _draft(client, prompt, fallback)


def draft_dues_confirmation(client: genai.Client | None, member: dict, amount: float, covers_full_year: bool) -> tuple[str, str]:
    period = "the full academic year" if covers_full_year else f"the {config.CURRENT_SEMESTER} semester"
    fallback = (
        "AED dues received — you're all set",
        f"Hi {member['full_name']},\n\nThis confirms we received your ${amount:,.2f} dues payment, "
        f"which covers {period}. You're all paid up!\n\nAED Treasurer Committee",
    )
    prompt = (
        f"Draft a dues confirmation email to {member['full_name']} confirming receipt of a "
        f"${amount:,.2f} dues payment that fully covers {period}."
    )
    return _draft(client, prompt, fallback)


def draft_dues_reminder(client: genai.Client | None, member: dict, amount_owed: float, semester: str) -> tuple[str, str]:
    fallback = (
        "Friendly reminder: AED dues outstanding",
        f"Hi {member['full_name']},\n\nOur records show you still owe ${amount_owed:,.2f} in AED dues "
        f"for {semester}. Please submit payment when you get a chance.\n\nAED Treasurer Committee",
    )
    prompt = (
        f"Draft a friendly (not stern) reminder email to {member['full_name']} that they still owe "
        f"${amount_owed:,.2f} in AED dues for {semester}."
    )
    return _draft(client, prompt, fallback)


def deliver_email(conn: sqlite3.Connection, member: dict, email_type: str, subject: str, body: str) -> None:
    recipient = member.get("email")
    mode = config.SEND_MODE if recipient else "review"

    if mode == "live":
        try:
            gmail_client.send_email(recipient, subject, body)
        except Exception as exc:  # noqa: BLE001 — fall back to a draft rather than silently dropping the email
            mode = "review"
            _write_draft(member, email_type, subject, f"[LIVE SEND FAILED: {exc}]\n\n{body}")
    if mode == "review":
        _write_draft(member, email_type, subject, body, missing_recipient=not bool(recipient))

    conn.execute(
        "INSERT INTO email_log (member_id, email_type, recipient_email, content, mode) VALUES (?, ?, ?, ?, ?)",
        (member["ut_id"], email_type, recipient, f"Subject: {subject}\n\n{body}", mode),
    )
    conn.commit()


def _write_draft(member: dict, email_type: str, subject: str, body: str, missing_recipient: bool = False) -> None:
    config.DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S%f")
    path = config.DRAFTS_DIR / f"{email_type}_{member['ut_id']}_{timestamp}.txt"
    to_line = member.get("email") or "(no email on file — draft only)"
    path.write_text(f"To: {to_line}\nSubject: {subject}\n\n{body}\n")


def handle_donation(conn: sqlite3.Connection, member: dict, amount: float, client: genai.Client | None = None) -> None:
    subject, body = draft_donation_thanks(client, member, amount)
    deliver_email(conn, member, "donation_thanks", subject, body)


def handle_dues_confirmation(conn: sqlite3.Connection, member: dict, amount: float, covers_full_year: bool, client: genai.Client | None = None) -> None:
    subject, body = draft_dues_confirmation(client, member, amount, covers_full_year)
    deliver_email(conn, member, "dues_confirmation", subject, body)


def send_reminders(conn: sqlite3.Connection, client: genai.Client | None = None) -> int:
    """Batch pass after reconciliation: remind everyone still owing dues,
    respecting REMINDER_COOLDOWN_DAYS so the daily job doesn't re-email daily."""
    cutoff = (datetime.utcnow() - timedelta(days=config.REMINDER_COOLDOWN_DAYS)).isoformat()
    rows = conn.execute(
        """SELECT m.*, ds.amount_owed AS owed, ds.semester AS ds_semester
           FROM dues_status ds JOIN members m ON m.ut_id = ds.member_id
           WHERE ds.amount_owed > 0 AND ds.semester = ?
             AND (ds.last_reminder_sent IS NULL OR ds.last_reminder_sent < ?)""",
        (config.CURRENT_SEMESTER, cutoff),
    ).fetchall()

    for row in rows:
        member = dict(row)
        subject, body = draft_dues_reminder(client, member, member["owed"], member["ds_semester"])
        deliver_email(conn, member, "dues_reminder", subject, body)
        conn.execute(
            "UPDATE dues_status SET last_reminder_sent = ? WHERE member_id = ? AND semester = ?",
            (datetime.utcnow().isoformat(), member["ut_id"], member["ds_semester"]),
        )
    conn.commit()
    return len(rows)
