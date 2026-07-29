import pytest

from dues_automation import rates


def test_get_dues_amounts_returns_seeded_defaults(temp_db):
    amounts = rates.get_dues_amounts(temp_db)
    assert amounts["pledge"] == {"semester": 150.0}
    assert amounts["active"] == {"semester": 130.0, "year": 220.0}


def test_set_rate_updates_semester_amount(temp_db):
    rates.set_rate(temp_db, "active", "semester", 135.0)
    amounts = rates.get_dues_amounts(temp_db)
    assert amounts["active"]["semester"] == 135.0
    assert amounts["active"]["year"] == 220.0  # untouched


def test_set_rate_rejects_pledge_year():
    with pytest.raises(ValueError):
        rates.set_rate(None, "pledge", "year", 300.0)  # rejected before touching the DB


def test_set_rate_unknown_status_raises(temp_db):
    with pytest.raises(ValueError):
        rates.set_rate(temp_db, "bogus", "semester", 100.0)
