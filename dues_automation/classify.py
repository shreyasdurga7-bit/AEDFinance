"""Section 4.5 dues/donation classification — explicit, testable business rules.

Deliberately NOT inferred by Claude on a case-by-case basis: dues amounts are
fixed and known in advance, so a mismatch should never be "guessed" into a
category. When in doubt, classify as a donation and flag for review — a human
can always recategorize, but the automation should never guess.
"""
from dataclasses import dataclass

from dues_automation.config import AMOUNT_TOLERANCE


@dataclass(frozen=True)
class Classification:
    payment_type: str          # 'dues', 'donation', or 'refund'
    covers_full_year: bool     # True only for active members paying the yearly rate
    needs_review: bool         # True if tolerance-matched, a refund, or a pledge paid a non-dues amount
    matched_amount: float | None  # the expected dues figure this payment was matched to, if any


def classify_payment(
    status: str, amount: float, dues_amounts: dict, tolerance: float = AMOUNT_TOLERANCE
) -> Classification:
    # A negative amount is a refund or chargeback, never dues or a donation —
    # always flagged for a human to reconcile manually rather than guessed at.
    if amount < 0:
        return Classification(payment_type="refund", covers_full_year=False, needs_review=True, matched_amount=None)

    if status not in ("pledge", "active"):
        raise ValueError(
            f"classify_payment does not apply to status={status!r}; "
            "alumni are excluded from reconciliation before classification runs"
        )

    def within_tolerance(a: float, b: float) -> bool:
        return abs(a - b) <= tolerance

    if status == "pledge":
        expected = dues_amounts["pledge"]["semester"]
        if within_tolerance(amount, expected):
            return Classification(
                payment_type="dues",
                covers_full_year=False,
                needs_review=(amount != expected),
                matched_amount=expected,
            )
        # Pledges may only pay per-semester. Any other amount — including one that
        # resembles a yearly rate — signals an error or a misunderstanding of the
        # rules, so it's always flagged for manual review, not just tolerance cases.
        return Classification(
            payment_type="donation",
            covers_full_year=False,
            needs_review=True,
            matched_amount=None,
        )

    semester_amt = dues_amounts["active"]["semester"]
    year_amt = dues_amounts["active"]["year"]

    if within_tolerance(amount, semester_amt):
        return Classification(
            payment_type="dues",
            covers_full_year=False,
            needs_review=(amount != semester_amt),
            matched_amount=semester_amt,
        )

    if within_tolerance(amount, year_amt):
        return Classification(
            payment_type="dues",
            covers_full_year=True,
            needs_review=(amount != year_amt),
            matched_amount=year_amt,
        )

    return Classification(
        payment_type="donation",
        covers_full_year=False,
        needs_review=False,
        matched_amount=None,
    )
