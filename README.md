# AED Dues Automation

Automates reconciling AED member dues against Venmo/Zelle transaction exports:
Gemini parses raw transaction rows, fuzzy-matching links them to members,
explicit business-rule logic (never Gemini guessing) classifies each payment
as dues or a donation, and the pipeline drafts (or, once configured, sends)
donation thank-yous, dues confirmations, and dues reminders.

**Status: trial run.** The database ships pre-seeded with a synthetic member
roster (see below) — no real AED member data has been loaded yet, and Gmail
sending defaults to a local dry-run mode. See "Known limitations" before using
this for real dues collection.

## Layout

```
dues_automation/
  schema.sql          # SQLite schema
  config.py            # env-driven settings
  db.py                 # connection + init helper
  seed_sample_db.py     # generates a synthetic member roster for dev/trial use
  parse.py               # Gemini parsing layer (Section 5.3)
  match.py               # fuzzy member matching (Section 5.4)
  classify.py            # dues/donation business rules (Section 4.5)
  rates.py                # configurable dues rates (dues_rates table) + CLI
  reconcile.py            # ingestion + reconciliation orchestration (Section 5.5)
  history.py               # per-member and chapter-wide multi-semester history
  visualize.py              # simple PDF bar chart of revenue by semester
  gmail_client.py          # send-only Gmail API wrapper
  get_gmail_token.py       # one-time local script to mint a Gmail refresh token
  send_emails.py            # donation/confirmation/reminder emails (Section 5.6)
  data/                      # synthetic CSV fixtures — safe to commit
  input/                      # drop REAL CSV exports here — gitignored
  tests/                        # pytest unit tests
.github/workflows/daily-reconcile.yml   # scheduled run
```

## Local setup

```bash
cd dues_automation
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in GEMINI_API_KEY etc.
```

### Seed the synthetic trial database

```bash
python -m dues_automation.seed_sample_db --count 40
```

This generates a fictional roster (random names, emails, phone numbers,
pledge/active/alumni status, class year, major) into `dues_automation.db`(main database).
**Never point this at a real roster file** — it's random data for testing the
pipeline before real member data is loaded.

### Run reconciliation against the example fixtures

```bash
cp dues_automation/data/example_venmo_export.csv dues_automation/input/
python -m dues_automation.reconcile
```

Prints a summary: total dues collected, total donations collected, total
dues outstanding, members overdue, and anything flagged `needs_review`
(uncertain member match, a tolerance-matched/anomalous amount, or a
negative-amount refund/chargeback — refunds are never auto-applied to a
balance and never trigger an email). With
`SEND_MODE=review` (the default), donation/confirmation/reminder emails are
written to `dues_automation/drafts/` instead of being sent.

### Update dues rates

Dues amounts live in the `dues_rates` table, not hardcoded in `config.py`, so
they can be changed without a code edit:

```bash
python -m dues_automation.rates show
python -m dues_automation.rates set active semester 135
```

Pledges can't be given a `year` rate (Section 4.5) — `set pledge year ...`
is rejected.

### View history

```bash
python -m dues_automation.history member <ut_id-or-name>   # one member's full record
python -m dues_automation.history summary                  # totals by semester, all time
```

`member` accepts either an exact `ut_id` or a name (fuzzy-matched the same
way ingestion matches transactions).

### Visualize revenue

```bash
python -m dues_automation.visualize
```

Reads whatever's in the database (e.g. after a trial run against the example
fixtures) and writes a simple one-page PDF bar chart of dues vs. donations
collected per semester to `dues_automation/reports/revenue_summary.pdf`
(gitignored — regenerate it whenever you want a fresh snapshot). Pass
`-o path/to/file.pdf` to write elsewhere.

### Run tests

```bash
pip install -r requirements.txt  # includes pytest
pytest dues_automation/tests/
```

## Secrets

| Variable | Where | Notes |
|---|---|---|
| `GEMINI_API_KEY` | `.env` locally, GitHub secret in Actions | Never hardcode, never log |
| `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` / `GMAIL_REFRESH_TOKEN` / `GMAIL_SENDER_EMAIL` | same | Send-only scope (`gmail.send`) — see below |
| `SEND_MODE` | `.env` / GitHub Actions repo variable | `review` (default, safe) or `live` |

`dues_automation.db`, `.env`, and anything in `dues_automation/input/` are
gitignored — only code, schema, docs, and the synthetic fixtures in
`dues_automation/data/` are ever committed.

## Enabling real Gmail sending (optional, do this later)

Sending is fully gated behind `SEND_MODE=live` and defaults to `review`
(local draft files only) — you don't need any of this to try the pipeline.
When you're ready:

1. Create a Google Cloud project at console.cloud.google.com (free).
2. Enable the **Gmail API** (APIs & Services → Library).
3. Configure the **OAuth consent screen** (External user type is fine),
   scope `https://www.googleapis.com/auth/gmail.send`, and add your own
   Gmail account as a test user — no Google verification review needed for
   this use case.
4. Create an **OAuth client ID** of type **Desktop app**
   (APIs & Services → Credentials) and download the JSON.
5. Run the one-time local authorization:
   ```bash
   python -m dues_automation.get_gmail_token path/to/client_secret_*.json
   ```
   This opens a browser for you to approve access, then prints the four
   values to put in `.env` (and as GitHub Actions secrets, if you turn on
   the scheduled workflow).
6. Flip `SEND_MODE=live` once you trust the matching/classification
   accuracy on a few real runs.

Creating the project, enabling the API, and this level of usage are all
free — Gmail API's free quota is far larger than a single chapter's email
volume.

## Known limitations (trial-run scope)

- **Real CSV column names are still unconfirmed.** `reconcile.py` handles
  arbitrary columns by serializing whatever's present into text for Gemini
  to interpret, so it should tolerate real exports, but the fixtures in
  `data/` are a best-effort approximation until a real export is available.
- **GitHub Actions persistence is not production-grade yet.** The workflow
  restores `dues_automation.db` from an `actions/cache` entry, which can be
  evicted (7-day unused limit, size limits). That's an acceptable trial-run
  tradeoff since the DB only holds synthetic data right now, but before
  relying on this for real financial records, move state to something
  durable (a private repo/branch dedicated to state, or external storage)
  rather than a cache.
- **Alumni are excluded from reconciliation entirely** — no `dues_status`
  rows are generated for them (their payments, if any, are logged as
  donations).
- **Pledge → active promotion mid-semester is treated as a closed
  transaction**: the prior $150 pledge payment is not rolled forward as
  credit toward the active rate.
