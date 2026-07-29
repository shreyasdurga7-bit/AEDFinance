# Example data — synthetic, for development only

`example_venmo_export.csv` and `example_zelle_export.csv` are **fictional test
fixtures**. Every name, amount, and note in these files is made up
(e.g. "Jamie Test", "Sam Example") — there is no real AED member data here,
and none should ever be added to this directory.

They exist so the ingestion parser, Claude parsing layer, fuzzy matcher, and
classification logic can be built and tested before a real Venmo/Zelle export
is available. Real column names should be verified against an actual export
once one exists — see Section 11 of the PRD.

Each file deliberately includes:
- a clean $150 pledge payment
- a clean $130 active-semester payment
- a clean $220 active-full-year payment
- a donation-sized amount that doesn't match any dues figure
- a payment identified only by a first name / nickname (fuzzy-match test)
- a payment with an irrelevant note/memo (emoji, "thanks!!!")
- a duplicate-looking transaction, to check the pipeline doesn't mishandle repeats
  (`example_venmo_export.csv` has the same name/amount on two different dates —
  these are two genuine separate payments and must both be counted;
  `example_zelle_export.csv` has one byte-for-byte identical row repeated —
  this is a single row accidentally duplicated in the export and must be
  counted only once)
- a payment within the $1 rounding/fee tolerance of a dues amount, to check it's
  flagged `needs_review` rather than silently accepted (Zelle file only)
- a malformed/incomplete row missing the amount or sender name
- a fully blank row
- a negative amount (a refund/chargeback), to check it's classified as
  `refund` — never dues or a donation, never auto-applied to a balance,
  always flagged for manual review

Plus a larger volume (~55-65 rows each) of ordinary clean/donation
transactions across many fictional names, to approximate a real chapter-sized
export rather than just the handful of edge cases above.

**Real exports go in `dues_automation/input/`** (per Section 5.2 of the PRD),
never here — that keeps these fixtures stable for testing regardless of what
real data looks like. `input/` and the SQLite database file are gitignored;
this `data/` directory is committed because it never contains real member
information.
