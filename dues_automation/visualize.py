"""Simple revenue summary — a one-page PDF bar chart of dues and donations
collected per semester. Handy for eyeballing results after a trial/test run
against the example fixtures.

Usage:
    python -m dues_automation.visualize [-o path/to/output.pdf]
"""
import argparse
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from dues_automation import config, db

DEFAULT_OUTPUT = config.BASE_DIR / "reports" / "revenue_summary.pdf"


def revenue_by_semester(conn: sqlite3.Connection) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            """SELECT semester,
                      SUM(CASE WHEN payment_type = 'dues' THEN amount ELSE 0 END) AS dues,
                      SUM(CASE WHEN payment_type = 'donation' THEN amount ELSE 0 END) AS donations
               FROM payments
               GROUP BY semester
               ORDER BY semester"""
        ).fetchall()
    ]


def generate_pdf(conn: sqlite3.Connection, output_path: Path) -> None:
    rows = revenue_by_semester(conn)
    if not rows:
        raise SystemExit("No payments on record yet — run reconciliation first.")

    semesters = [r["semester"] for r in rows]
    dues = [r["dues"] for r in rows]
    donations = [r["donations"] for r in rows]
    x = range(len(semesters))

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(x, dues, label="Dues", color="#4C72B0")
    ax.bar(x, donations, bottom=dues, label="Donations", color="#DD8452")
    ax.set_xticks(list(x))
    ax.set_xticklabels(semesters)
    ax.set_ylabel("Revenue ($)")
    ax.set_title("AED Revenue by Semester")
    ax.legend()
    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    db.init_db()
    with db.get_connection() as conn:
        generate_pdf(conn, args.output)
