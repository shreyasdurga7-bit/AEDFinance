from dues_automation import classify, config, parse, rates, reconcile


def _stub_parse_batch(canned):
    def _fake(raw_texts, conn, client=None, delay_seconds=0.0):
        results = [parse.ParseResult(status="success", parsed=c) for c in canned]
        for raw, r in zip(raw_texts, results):
            conn.execute(
                "INSERT INTO parse_log (raw_input, parsed_output, status) VALUES (?, ?, ?)",
                (raw, str(r.parsed), r.status),
            )
        conn.commit()
        return results

    return _fake


def _silence_emails(monkeypatch):
    monkeypatch.setattr(reconcile.send_emails, "handle_donation", lambda *a, **k: None)
    monkeypatch.setattr(reconcile.send_emails, "handle_dues_confirmation", lambda *a, **k: None)
    monkeypatch.setattr(reconcile.send_emails, "send_reminders", lambda *a, **k: 0)


def test_reconciliation_math_dues_vs_donations(temp_db, monkeypatch, tmp_path):
    conn = temp_db
    conn.execute("INSERT INTO members (ut_id, full_name, email, status) VALUES ('jat1001', 'Jamie Test', 'jamie@example.edu', 'pledge')")
    conn.execute("INSERT INTO members (ut_id, full_name, email, status) VALUES ('sbe2002', 'Sam Example', 'sam@example.edu', 'active')")
    conn.execute(
        "INSERT INTO dues_status (member_id, semester, amount_owed, amount_paid) VALUES ('jat1001', ?, 150, 0)",
        (config.CURRENT_SEMESTER,),
    )
    conn.execute(
        "INSERT INTO dues_status (member_id, semester, amount_owed, amount_paid) VALUES ('sbe2002', ?, 130, 0)",
        (config.CURRENT_SEMESTER,),
    )
    conn.commit()

    csv_path = tmp_path / "test.csv"
    csv_path.write_text("from,amount\nJamie Test,150\nSam Example,25\n")

    canned = [
        {"name": "Jamie Test", "amount": 150, "date": "2026-09-01", "note": None},
        {"name": "Sam Example", "amount": 25, "date": "2026-09-02", "note": None},
    ]
    monkeypatch.setattr(reconcile.parse, "parse_batch", _stub_parse_batch(canned))
    _silence_emails(monkeypatch)

    summary = reconcile.process_csv(csv_path, conn)

    assert summary.dues_committed == 150      # Jamie's exact pledge payment
    assert summary.donations_committed == 25  # Sam's $25 doesn't match any active dues figure

    jamie_owed = conn.execute("SELECT amount_owed FROM dues_status WHERE member_id = 'jat1001'").fetchone()[0]
    assert jamie_owed == 0

    sam_owed = conn.execute("SELECT amount_owed FROM dues_status WHERE member_id = 'sbe2002'").fetchone()[0]
    assert sam_owed == 130  # donation never partially credits dues owed


def test_full_year_payment_splits_across_both_semesters(temp_db):
    conn = temp_db
    conn.execute("INSERT INTO members (ut_id, full_name, status) VALUES ('cxs3003', 'Casey Sample', 'active')")
    conn.commit()

    member = {"ut_id": "cxs3003", "status": "active"}
    dues_amounts = rates.get_dues_amounts(conn)
    cls = classify.classify_payment("active", 220.0, dues_amounts)
    fully_resolved = reconcile.apply_dues_payment(conn, member, cls, 220.0, dues_amounts)

    assert fully_resolved is True
    rows = conn.execute(
        "SELECT semester, amount_owed, amount_paid FROM dues_status WHERE member_id = 'cxs3003' ORDER BY semester"
    ).fetchall()
    assert len(rows) == 2
    for row in rows:
        assert row["amount_owed"] == 0
        assert row["amount_paid"] == 110.0


def test_low_confidence_match_never_updates_dues_status(temp_db, monkeypatch, tmp_path):
    conn = temp_db
    conn.execute("INSERT INTO members (ut_id, full_name, email, status) VALUES ('jat1001', 'Jamie Test', 'jamie@example.edu', 'pledge')")
    conn.execute(
        "INSERT INTO dues_status (member_id, semester, amount_owed, amount_paid) VALUES ('jat1001', ?, 150, 0)",
        (config.CURRENT_SEMESTER,),
    )
    conn.commit()

    csv_path = tmp_path / "ambiguous.csv"
    csv_path.write_text("from,amount\nJ,150\n")

    canned = [{"name": "J", "amount": 150, "date": "2026-09-01", "note": None}]
    monkeypatch.setattr(reconcile.parse, "parse_batch", _stub_parse_batch(canned))
    _silence_emails(monkeypatch)

    reconcile.process_csv(csv_path, conn)

    owed = conn.execute("SELECT amount_owed FROM dues_status WHERE member_id = 'jat1001'").fetchone()[0]
    assert owed == 150  # untouched — a single letter must never auto-confirm a match


def test_negative_amount_is_flagged_refund_and_never_applied(temp_db, monkeypatch, tmp_path):
    conn = temp_db
    conn.execute("INSERT INTO members (ut_id, full_name, email, status) VALUES ('jat1001', 'Jamie Test', 'jamie@example.edu', 'active')")
    conn.execute(
        "INSERT INTO dues_status (member_id, semester, amount_owed, amount_paid) VALUES ('jat1001', ?, 130, 0)",
        (config.CURRENT_SEMESTER,),
    )
    conn.commit()

    csv_path = tmp_path / "refund.csv"
    csv_path.write_text("from,amount\nJamie Test,-20\n")

    canned = [{"name": "Jamie Test", "amount": -20, "date": "2026-09-01", "note": "refund"}]
    monkeypatch.setattr(reconcile.parse, "parse_batch", _stub_parse_batch(canned))
    _silence_emails(monkeypatch)

    summary = reconcile.process_csv(csv_path, conn)

    assert summary.dues_committed == 0
    assert summary.donations_committed == 0
    assert len(summary.rows_flagged_refund) == 1
    assert summary.rows_flagged_refund[0]["amount"] == -20

    owed = conn.execute("SELECT amount_owed FROM dues_status WHERE member_id = 'jat1001'").fetchone()[0]
    assert owed == 130  # a refund must never adjust a member's balance automatically

    payment_type, needs_review = conn.execute(
        "SELECT payment_type, needs_review FROM payments WHERE member_id = 'jat1001'"
    ).fetchone()
    assert payment_type == "refund"
    assert needs_review == 1
