"""Configurable dues rates — read from/written to the dues_rates table
instead of hardcoded in config.py, so next year's treasurer can update the
$130/$150/$220 figures without touching code.

Usage:
    python -m dues_automation.rates show
    python -m dues_automation.rates set active semester 135
"""
import argparse
import sqlite3

from dues_automation import db


def get_dues_amounts(conn: sqlite3.Connection) -> dict:
    """Returns the same shape the rest of the pipeline expects:
    {"pledge": {"semester": 150.0}, "active": {"semester": 130.0, "year": 220.0}}"""
    rows = conn.execute("SELECT status, semester_amount, year_amount FROM dues_rates").fetchall()
    amounts: dict = {}
    for row in rows:
        entry = {"semester": row["semester_amount"]}
        if row["year_amount"] is not None:
            entry["year"] = row["year_amount"]
        amounts[row["status"]] = entry
    return amounts


def set_rate(conn: sqlite3.Connection, status: str, period: str, amount: float) -> None:
    if status == "pledge" and period == "year":
        raise ValueError("Pledges cannot pay per-year — see Section 4.5 of the PRD.")
    column = "semester_amount" if period == "semester" else "year_amount"
    cur = conn.execute(
        f"UPDATE dues_rates SET {column} = ?, updated_at = CURRENT_TIMESTAMP WHERE status = ?",
        (amount, status),
    )
    if cur.rowcount == 0:
        raise ValueError(f"Unknown status {status!r}")
    conn.commit()


def _print_rates(conn: sqlite3.Connection) -> None:
    for status, amounts in get_dues_amounts(conn).items():
        parts = [f"semester=${amounts['semester']:.2f}"]
        if "year" in amounts:
            parts.append(f"year=${amounts['year']:.2f}")
        print(f"{status}: {', '.join(parts)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show", help="Print current dues rates")
    set_p = sub.add_parser("set", help="Update a dues rate")
    set_p.add_argument("status", choices=["pledge", "active"])
    set_p.add_argument("period", choices=["semester", "year"])
    set_p.add_argument("amount", type=float)
    args = parser.parse_args()

    db.init_db()
    with db.get_connection() as conn:
        if args.command == "show":
            _print_rates(conn)
        else:
            set_rate(conn, args.status, args.period, args.amount)
            print(f"Updated {args.status} {args.period} rate to ${args.amount:.2f}\n")
            _print_rates(conn)
