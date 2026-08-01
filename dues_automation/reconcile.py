"""Section 5.5 — ingestion, matching, classification, and reconciliation.

Pipeline per CSV file: read rows (skip malformed ones) -> serialize each row to
raw text -> Gemini-parse -> fuzzy-match to a member -> classify dues/donation
-> write payments -> update dues_status -> print a summary report.
"""
import argparse
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from google import genai

from dues_automation import classify, config, db, match, parse, rates, send_emails

SEMESTER_RE = re.compile(r"^(Fall|Spring)(\d{4})$")


def sibling_semester(semester: str) -> str | None:
    """The other semester of the same academic year (Fall2026 <-> Spring2027)."""
    m = SEMESTER_RE.match(semester)
    if not m:
        return None
    term, year = m.group(1), int(m.group(2))
    if term == "Fall":
        return f"Spring{year + 1}"
    return f"Fall{year - 1}"


def row_to_raw_text(row: pd.Series) -> str:
    """Serialize a CSV row into 'column: value' text, regardless of the
    source platform's actual column names — this is what gets sent to Gemini."""
    parts = [f"{col}: {val}" for col, val in row.items() if pd.notna(val) and str(val).strip() != ""]
    return "; ".join(parts)


@dataclass
class IngestSummary:
    rows_seen: int = 0
    rows_skipped_malformed: int = 0
    rows_skipped_duplicate: int = 0
    rows_parse_failed: int = 0
    rows_no_match: int = 0
    rows_needs_match_review: list = field(default_factory=list)
    rows_needs_amount_review: list = field(default_factory=list)
    rows_flagged_refund: list = field(default_factory=list)
    dues_committed: float = 0.0
    donations_committed: float = 0.0


def load_csv_rows(csv_path: Path, conn: sqlite3.Connection) -> tuple[list[pd.Series], int]:
    """Load a CSV with pandas; malformed rows are logged and skipped rather
    than crashing the batch. Venmo/Zelle exports occasionally have a stray
    row with more fields than the header (a rogue comma in a note, a
    corrupted line) — the default C parser aborts the *entire file* on that,
    so bad lines are routed to on_bad_lines and logged instead of raising."""
    bad_lines: list[list[str]] = []

    def _capture_bad_line(bad_line: list[str]) -> None:
        bad_lines.append(bad_line)

    df = pd.read_csv(
        csv_path, dtype=str, keep_default_na=True,
        engine="python", on_bad_lines=_capture_bad_line,
    )

    for bad_line in bad_lines:
        conn.execute(
            "INSERT INTO parse_log (raw_input, parsed_output, status) VALUES (?, ?, ?)",
            (",".join(bad_line), "malformed row: unexpected number of fields", "failed"),
        )

    valid_rows = []
    skipped = len(bad_lines)
    for _, row in df.iterrows():
        if row.isna().all():
            conn.execute(
                "INSERT INTO parse_log (raw_input, parsed_output, status) VALUES (?, ?, ?)",
                (str(row.to_dict()), "empty row", "failed"),
            )
            skipped += 1
            continue
        valid_rows.append(row)
    conn.commit()
    return valid_rows, skipped


def load_members(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM members").fetchall()]


def _get_or_create_dues_status(conn: sqlite3.Connection, member_id: str, semester: str, default_owed: float) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM dues_status WHERE member_id = ? AND semester = ?", (member_id, semester)
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO dues_status (member_id, semester, amount_owed, amount_paid) VALUES (?, ?, ?, 0)",
            (member_id, semester, default_owed),
        )
        row = conn.execute(
            "SELECT * FROM dues_status WHERE member_id = ? AND semester = ?", (member_id, semester)
        ).fetchone()
    return row


def apply_dues_payment(
    conn: sqlite3.Connection, member: dict, cls: classify.Classification, amount: float, dues_amounts: dict
) -> bool:
    """Credit a confirmed dues payment against dues_status. A full-year
    payment ($220) is less than two semesters at the regular rate ($260) —
    that's the discount for paying upfront — so per Section 5.5 it zeros out
    amount_owed for both semesters directly rather than being proportionally
    subtracted. amount_paid is still split evenly across the two rows for
    audit purposes. Returns True if the payment fully resolves amount_owed
    (triggers the dues confirmation email in Section 5.6)."""
    per_semester_default = dues_amounts[member["status"]]["semester"]

    if cls.covers_full_year:
        half = amount / 2
        for semester in (config.CURRENT_SEMESTER, sibling_semester(config.CURRENT_SEMESTER)):
            if semester is None:
                continue
            row = _get_or_create_dues_status(conn, member["ut_id"], semester, per_semester_default)
            new_paid = row["amount_paid"] + half
            conn.execute(
                "UPDATE dues_status SET amount_paid = ?, amount_owed = 0 WHERE member_id = ? AND semester = ?",
                (new_paid, member["ut_id"], semester),
            )
        return True

    row = _get_or_create_dues_status(conn, member["ut_id"], config.CURRENT_SEMESTER, per_semester_default)
    new_paid = row["amount_paid"] + amount
    new_owed = max(0.0, row["amount_owed"] - amount)
    conn.execute(
        "UPDATE dues_status SET amount_paid = ?, amount_owed = ? WHERE member_id = ? AND semester = ?",
        (new_paid, new_owed, member["ut_id"], config.CURRENT_SEMESTER),
    )
    return new_owed == 0


def process_csv(csv_path: Path, conn: sqlite3.Connection, client: genai.Client | None = None) -> IngestSummary:
    summary = IngestSummary()
    rows, skipped_malformed = load_csv_rows(csv_path, conn)
    summary.rows_seen = len(rows)
    summary.rows_skipped_malformed = skipped_malformed

    raw_texts = [row_to_raw_text(r) for r in rows]

    seen_raw = set()
    deduped = []
    for raw_text in raw_texts:
        if raw_text in seen_raw:
            summary.rows_skipped_duplicate += 1
            conn.execute(
                "INSERT INTO parse_log (raw_input, parsed_output, status) VALUES (?, ?, ?)",
                (raw_text, "exact duplicate row in same file, skipped", "failed"),
            )
            continue
        seen_raw.add(raw_text)
        deduped.append(raw_text)
    conn.commit()

    parse_results = parse.parse_batch(deduped, conn, client=client)
    members = load_members(conn)
    dues_amounts = rates.get_dues_amounts(conn)

    for raw_text, result in zip(deduped, parse_results):
        if result.status != "success" or result.parsed is None:
            summary.rows_parse_failed += 1
            continue

        parsed = result.parsed
        name = parsed.get("name")
        amount = parsed.get("amount")
        raw_date = parsed.get("date")

        if amount is None:
            summary.rows_parse_failed += 1
            continue
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            summary.rows_parse_failed += 1
            continue

        m = match.find_best_match(name, members)

        if not m.has_candidate:
            summary.rows_no_match += 1
            conn.execute(
                "INSERT INTO parse_log (raw_input, parsed_output, status) VALUES (?, ?, ?)",
                (raw_text, str(parsed), "low_confidence"),
            )
            continue

        member = next(mm for mm in members if mm["ut_id"] == m.member_id)

        if not m.is_confident:
            # Low-confidence member match: recorded for audit, but never
            # auto-committed to a member's dues balance (Section 5.4).
            summary.rows_needs_match_review.append(
                {"raw_text": raw_text, "guessed_name": m.matched_name, "confidence": m.confidence, "amount": amount}
            )
            conn.execute(
                """INSERT INTO payments
                   (member_id, amount, date_paid, semester, payment_type, covers_full_year,
                    needs_review, source_text, match_confidence)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                (
                    member["ut_id"], amount, raw_date or "", config.CURRENT_SEMESTER,
                    "donation",  # placeholder classification pending human confirmation of identity
                    0, raw_text, m.confidence,
                ),
            )
            continue

        if amount < 0:
            # A refund or chargeback — never dues or a donation, and never
            # auto-applied to a balance. Always flagged for manual review.
            cls = classify.Classification(payment_type="refund", covers_full_year=False, needs_review=True, matched_amount=None)
        elif member["status"] == "alumni":
            # Alumni are excluded from dues reconciliation; still logged as a donation.
            cls = classify.Classification(payment_type="donation", covers_full_year=False, needs_review=False, matched_amount=None)
        else:
            cls = classify.classify_payment(member["status"], amount, dues_amounts)

        conn.execute(
            """INSERT INTO payments
               (member_id, amount, date_paid, semester, payment_type, covers_full_year,
                needs_review, source_text, match_confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                member["ut_id"], amount, raw_date or "", config.CURRENT_SEMESTER,
                cls.payment_type, int(cls.covers_full_year), int(cls.needs_review),
                raw_text, m.confidence,
            ),
        )

        if cls.payment_type == "refund":
            summary.rows_flagged_refund.append({"member": member["full_name"], "amount": amount})
        elif cls.needs_review:
            summary.rows_needs_amount_review.append(
                {"member": member["full_name"], "amount": amount, "payment_type": cls.payment_type}
            )

        if cls.payment_type == "dues" and member["status"] != "alumni":
            fully_resolved = apply_dues_payment(conn, member, cls, amount, dues_amounts)
            summary.dues_committed += amount
            if fully_resolved:
                send_emails.handle_dues_confirmation(conn, member, amount, cls.covers_full_year, client=client)
        elif cls.payment_type == "donation":
            summary.donations_committed += amount
            send_emails.handle_donation(conn, member, amount, client=client)
        # refund: already recorded in payments and flagged above — no email,
        # no dues/donation total change, never auto-applied to a balance.

    conn.commit()
    return summary


def print_report(conn: sqlite3.Connection, summary: IngestSummary) -> None:
    outstanding = conn.execute(
        """SELECT m.full_name, ds.amount_owed FROM dues_status ds
           JOIN members m ON m.ut_id = ds.member_id
           WHERE ds.semester = ? AND ds.amount_owed > 0
           ORDER BY ds.amount_owed DESC""",
        (config.CURRENT_SEMESTER,),
    ).fetchall()
    total_outstanding = sum(r["amount_owed"] for r in outstanding)

    deadline = datetime.strptime(config.DUES_DEADLINE, "%Y-%m-%d").date()
    overdue_cutoff = deadline + timedelta(days=config.OVERDUE_GRACE_DAYS)
    is_overdue = date.today() > overdue_cutoff

    print("=" * 60)
    print(f"AED Dues Reconciliation — {config.CURRENT_SEMESTER}")
    print("=" * 60)
    print(f"Rows seen:              {summary.rows_seen}")
    print(f"Skipped (malformed):    {summary.rows_skipped_malformed}")
    print(f"Skipped (duplicate):    {summary.rows_skipped_duplicate}")
    print(f"Parse failures:         {summary.rows_parse_failed}")
    print(f"No plausible match:     {summary.rows_no_match}")
    print()
    print(f"Total dues collected:      ${summary.dues_committed:,.2f}")
    print(f"Total donations collected: ${summary.donations_committed:,.2f}")
    print(f"Total dues outstanding:    ${total_outstanding:,.2f}")
    print()

    if is_overdue and outstanding:
        print(f"Members overdue (past {overdue_cutoff.isoformat()}):")
        for r in outstanding:
            print(f"  - {r['full_name']}: ${r['amount_owed']:,.2f} owed")
    elif outstanding:
        print(f"Members with balance owed (not yet past the {overdue_cutoff.isoformat()} overdue cutoff):")
        for r in outstanding:
            print(f"  - {r['full_name']}: ${r['amount_owed']:,.2f} owed")

    if summary.rows_needs_match_review:
        print()
        print("NEEDS REVIEW — uncertain member match (never auto-committed):")
        for item in summary.rows_needs_match_review:
            print(f"  - guessed '{item['guessed_name']}' (confidence {item['confidence']:.0%}), ${item['amount']:,.2f}: {item['raw_text']}")

    if summary.rows_needs_amount_review:
        print()
        print("NEEDS REVIEW — tolerance-matched or anomalous amount:")
        for item in summary.rows_needs_amount_review:
            print(f"  - {item['member']}: ${item['amount']:,.2f} classified as {item['payment_type']}")

    if summary.rows_flagged_refund:
        print()
        print("NEEDS REVIEW — refund or negative amount (never auto-applied to a balance):")
        for item in summary.rows_flagged_refund:
            print(f"  - {item['member']}: ${item['amount']:,.2f}")


def run(csv_paths: list[Path]) -> None:
    db.init_db()
    with db.get_connection() as conn:
        client = genai.Client(api_key=config.GEMINI_API_KEY) if config.GEMINI_API_KEY else None
        combined = IngestSummary()
        for csv_path in csv_paths:
            s = process_csv(csv_path, conn, client=client)
            for f in ("rows_seen", "rows_skipped_malformed", "rows_skipped_duplicate",
                      "rows_parse_failed", "rows_no_match", "dues_committed", "donations_committed"):
                setattr(combined, f, getattr(combined, f) + getattr(s, f))
            combined.rows_needs_match_review += s.rows_needs_match_review
            combined.rows_needs_amount_review += s.rows_needs_amount_review
            combined.rows_flagged_refund += s.rows_flagged_refund
        reminders_sent = send_emails.send_reminders(conn, client=client)
        print_report(conn, combined)
        print(f"\nReminder emails drafted/sent (SEND_MODE={config.SEND_MODE}): {reminders_sent}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_files", nargs="*", help="CSV files to process; defaults to everything in input/")
    args = parser.parse_args()

    if args.csv_files:
        paths = [Path(p) for p in args.csv_files]
    else:
        paths = sorted(config.INPUT_DIR.glob("*.csv"))

    if not paths:
        print(f"No CSV files found in {config.INPUT_DIR} — nothing to do.")
    else:
        run(paths)
