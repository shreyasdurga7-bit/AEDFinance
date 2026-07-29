import pytest

from dues_automation.classify import classify_payment

DUES_AMOUNTS = {
    "pledge": {"semester": 150.0},
    "active": {"semester": 130.0, "year": 220.0},
}


def test_pledge_exact_dues():
    c = classify_payment("pledge", 150.0, DUES_AMOUNTS)
    assert c.payment_type == "dues"
    assert c.covers_full_year is False
    assert c.needs_review is False


def test_pledge_tolerance_matched_flagged():
    c = classify_payment("pledge", 150.75, DUES_AMOUNTS)
    assert c.payment_type == "dues"
    assert c.needs_review is True


def test_pledge_wrong_amount_is_donation_and_flagged():
    c = classify_payment("pledge", 220.0, DUES_AMOUNTS)  # a pledge attempting the active yearly rate
    assert c.payment_type == "donation"
    assert c.needs_review is True  # PRD: always flagged, not just tolerance cases


def test_pledge_small_donation():
    c = classify_payment("pledge", 25.0, DUES_AMOUNTS)
    assert c.payment_type == "donation"
    assert c.needs_review is True


def test_active_exact_semester_dues():
    c = classify_payment("active", 130.0, DUES_AMOUNTS)
    assert c.payment_type == "dues"
    assert c.covers_full_year is False
    assert c.needs_review is False


def test_active_tolerance_matched_semester():
    c = classify_payment("active", 130.99, DUES_AMOUNTS)
    assert c.payment_type == "dues"
    assert c.needs_review is True


def test_active_exact_year_dues():
    c = classify_payment("active", 220.0, DUES_AMOUNTS)
    assert c.payment_type == "dues"
    assert c.covers_full_year is True
    assert c.needs_review is False


def test_active_tolerance_matched_year():
    c = classify_payment("active", 220.50, DUES_AMOUNTS)
    assert c.payment_type == "dues"
    assert c.covers_full_year is True
    assert c.needs_review is True


def test_active_mismatched_amount_is_donation():
    c = classify_payment("active", 25.0, DUES_AMOUNTS)
    assert c.payment_type == "donation"
    assert c.covers_full_year is False


def test_amount_outside_tolerance_not_matched():
    c = classify_payment("active", 132.0, DUES_AMOUNTS)  # $2 off — outside the default $1 tolerance
    assert c.payment_type == "donation"


def test_alumni_status_rejected():
    with pytest.raises(ValueError):
        classify_payment("alumni", 150.0, DUES_AMOUNTS)


def test_negative_amount_is_refund_for_active():
    c = classify_payment("active", -20.0, DUES_AMOUNTS)
    assert c.payment_type == "refund"
    assert c.needs_review is True
    assert c.covers_full_year is False


def test_negative_amount_is_refund_for_pledge():
    c = classify_payment("pledge", -150.0, DUES_AMOUNTS)
    assert c.payment_type == "refund"
    assert c.needs_review is True


def test_configurable_rate_changes_classification():
    # If the dues_rates table is updated (e.g. next year's treasurer raises
    # active semester dues to $135), classification must follow the new
    # figure rather than a hardcoded constant.
    custom_amounts = {"pledge": {"semester": 150.0}, "active": {"semester": 135.0, "year": 220.0}}
    c = classify_payment("active", 135.0, custom_amounts)
    assert c.payment_type == "dues"
    assert c.needs_review is False
    # The old $130 rate should no longer exact-match under the new rate.
    c_old_rate = classify_payment("active", 130.0, custom_amounts)
    assert c_old_rate.payment_type == "donation"
