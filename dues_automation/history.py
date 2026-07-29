"""Multi-semester history reporting. dues_status and payments are already
tracked per semester, so a member's full giving history — or a chapter-wide
breakdown across every semester on record — is just a couple of queries.

Usage:
    python -m dues_automation.history member <ut_id-or-name>
    python -m dues_automation.history summary
"""
import argparse
import sqlite3

from dues_automation import db, match


def member_payment_history(conn: sqlite3.Connection, ut_id: str) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            """SELECT date_paid, amount, payment_type, semester, needs_review
               FROM payments WHERE member_id = ? ORDER BY date_paid""",
            (ut_id,),
        ).fetchall()
    ]


def member_dues_history(conn: sqlite3.Connection, ut_id: str) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            """SELECT semester, amount_owed, amount_paid
               FROM dues_status WHERE member_id = ? ORDER BY semester""",
            (ut_id,),
        ).fetchall()
    ]


def resolve_member(conn: sqlite3.Connection, query: str) -> dict | None:
    """Accept an exact ut_id, or fuzzy-match a name against the roster."""
    row = conn.execute("SELECT * FROM members WHERE ut_id = ?", (query,)).fetchone()
    if row is not None:
        return dict(row)

    members = [dict(r) for r in conn.execute("SELECT * FROM members").fetchall()]
    result = match.find_best_match(query, members, threshold=70)
    if result.has_candidate:
        return next(m for m in members if m["ut_id"] == result.member_id)
    return None


def print_member_history(conn: sqlite3.Connection, query: str) -> None:
    member = resolve_member(conn, query)
    if member is None:
        print(f"No member found matching {query!r}")
        return

    print(f"{member['full_name']} ({member['ut_id']}) — {member['status']}")
    print()

    dues_rows = member_dues_history(conn, member["ut_id"])
    if dues_rows:
        print("Dues status by semester:")
        for row in dues_rows:
            print(f"  {row['semester']:<10} owed ${row['amount_owed']:,.2f}   paid ${row['amount_paid']:,.2f}")
    else:
        print("No dues_status rows (alumni, or never reconciled).")

    print()
    payment_rows = member_payment_history(conn, member["ut_id"])
    if payment_rows:
        print("Payment history:")
        for row in payment_rows:
            flag = "  [needs review]" if row["needs_review"] else ""
            print(f"  {row['date_paid']}  {row['semester']:<10} {row['payment_type']:<9} ${row['amount']:,.2f}{flag}")
    else:
        print("No payments on record.")


def print_chapter_summary(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """SELECT semester,
                  SUM(CASE WHEN payment_type = 'dues' THEN amount ELSE 0 END) AS dues_collected,
                  SUM(CASE WHEN payment_type = 'donation' THEN amount ELSE 0 END) AS donations_collected,
                  SUM(CASE WHEN payment_type = 'refund' THEN amount ELSE 0 END) AS refunds
           FROM payments
           GROUP BY semester
           ORDER BY semester"""
    ).fetchall()

    if not rows:
        print("No payments on record yet.")
        return

    print("Semester-by-semester totals (all time):")
    for row in rows:
        print(
            f"  {row['semester']:<10} dues ${row['dues_collected']:,.2f}   "
            f"donations ${row['donations_collected']:,.2f}   refunds ${row['refunds']:,.2f}"
        )

    outstanding = conn.execute(
        """SELECT semester, SUM(amount_owed) AS total_owed
           FROM dues_status WHERE amount_owed > 0 GROUP BY semester ORDER BY semester"""
    ).fetchall()
    if outstanding:
        print()
        print("Outstanding balances by semester:")
        for row in outstanding:
            print(f"  {row['semester']:<10} ${row['total_owed']:,.2f} still owed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    member_p = sub.add_parser("member", help="Show one member's full payment history")
    member_p.add_argument("query", help="A ut_id, or a name to fuzzy-match")
    sub.add_parser("summary", help="Chapter-wide totals broken out by semester")
    args = parser.parse_args()

    db.init_db()
    with db.get_connection() as conn:
        if args.command == "member":
            print_member_history(conn, args.query)
        else:
            print_chapter_summary(conn)
