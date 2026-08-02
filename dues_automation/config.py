"""Central config for the dues automation pipeline. Reads from environment / .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DB_PATH = os.environ.get("DUES_DB_PATH", str(BASE_DIR / "dues_automation.db"))
INPUT_DIR = Path(os.environ.get("DUES_INPUT_DIR", str(BASE_DIR / "input")))

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")

# Section 5.4 — matches below this score are flagged for manual review, never auto-committed.
FUZZY_MATCH_THRESHOLD = int(os.environ.get("DUES_FUZZY_THRESHOLD", "85"))

# Section 4.5 — the tolerance allowed for payment-app rounding/fee quirks.
# Dues amounts themselves live in the dues_rates table (see rates.py), not
# here, so they can be updated without a code change.
AMOUNT_TOLERANCE = float(os.environ.get("DUES_AMOUNT_TOLERANCE", "1.0"))

# Section 5.6 — dry-run gate. "review" writes drafts/logs only; "live" actually sends via Gmail.
SEND_MODE = os.environ.get("SEND_MODE", "review")
assert SEND_MODE in ("review", "live"), "SEND_MODE must be 'review' or 'live'"

DRAFTS_DIR = Path(os.environ.get("DUES_DRAFTS_DIR", str(BASE_DIR / "drafts")))

GMAIL_CLIENT_ID = os.environ.get("GMAIL_CLIENT_ID")
GMAIL_CLIENT_SECRET = os.environ.get("GMAIL_CLIENT_SECRET")
GMAIL_REFRESH_TOKEN = os.environ.get("GMAIL_REFRESH_TOKEN")
GMAIL_SENDER_EMAIL = os.environ.get("GMAIL_SENDER_EMAIL")

CURRENT_SEMESTER = os.environ.get("DUES_CURRENT_SEMESTER", "Fall2026")

# Chapter-wide dues deadline for the current semester (same for every member).
# "Overdue" in the reconciliation report means amount_owed > 0 more than
# OVERDUE_GRACE_DAYS after this date.
DUES_DEADLINE = os.environ.get("DUES_DEADLINE", "2026-09-15")
OVERDUE_GRACE_DAYS = int(os.environ.get("DUES_OVERDUE_GRACE_DAYS", "14"))

# Don't re-send a reminder to the same member more often than this, even if
# the daily job runs every day and they still owe money.
REMINDER_COOLDOWN_DAYS = int(os.environ.get("DUES_REMINDER_COOLDOWN_DAYS", "7"))
