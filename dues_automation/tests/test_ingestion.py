import pandas as pd

from dues_automation.reconcile import load_csv_rows, row_to_raw_text, sibling_semester


def test_load_csv_rows_skips_ragged_row_with_too_many_fields(temp_db, tmp_path):
    # A row with more fields than the header (e.g. a stray comma) used to
    # crash pandas' C parser for the *entire file* — it must instead be
    # logged and skipped, leaving the well-formed rows intact.
    csv_path = tmp_path / "messy.csv"
    csv_path.write_text("name,amount\nJamie Test,150\n,,\nSam Example,130\n")
    rows, skipped = load_csv_rows(csv_path, temp_db)
    assert len(rows) == 2
    assert skipped == 1

    logged = temp_db.execute("SELECT * FROM parse_log").fetchall()
    assert len(logged) == 1
    assert logged[0]["status"] == "failed"


def test_load_csv_rows_skips_fully_blank_row(temp_db, tmp_path):
    csv_path = tmp_path / "blank.csv"
    csv_path.write_text("name,amount\nJamie Test,150\n,\nSam Example,130\n")
    rows, skipped = load_csv_rows(csv_path, temp_db)
    assert len(rows) == 2
    assert skipped == 1


def test_load_csv_rows_handles_missing_columns(temp_db, tmp_path):
    csv_path = tmp_path / "missing_cols.csv"
    csv_path.write_text("date,description,amount\n2026-09-01,payment,150\n")
    rows, skipped = load_csv_rows(csv_path, temp_db)
    assert len(rows) == 1
    assert skipped == 0


def test_row_to_raw_text_skips_nan_fields():
    row = pd.Series({"name": "Jamie Test", "amount": 150, "note": None})
    text = row_to_raw_text(row)
    assert "name: Jamie Test" in text
    assert "amount: 150" in text
    assert "note" not in text


def test_sibling_semester_pairs_within_academic_year():
    assert sibling_semester("Fall2026") == "Spring2027"
    assert sibling_semester("Spring2027") == "Fall2026"


def test_sibling_semester_unknown_format_returns_none():
    assert sibling_semester("Summer2026") is None
