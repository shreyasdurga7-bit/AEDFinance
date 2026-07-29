-- AED Dues Automation — SQLite schema
-- See dues_automation/README.md for setup instructions.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS members (
    ut_id TEXT PRIMARY KEY,     -- UT Austin EID, e.g. "sd43433" — the member's natural key
    full_name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    status TEXT CHECK(status IN ('active','pledge','alumni')) DEFAULT 'active',
    year TEXT,                 -- class year, e.g. "Freshman", "Sophomore", "Junior", "Senior"
    major TEXT,
    semester_joined TEXT
);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY,
    member_id TEXT REFERENCES members(ut_id),
    amount REAL NOT NULL,
    date_paid TEXT NOT NULL,
    semester TEXT NOT NULL,
    payment_type TEXT CHECK(payment_type IN ('dues','donation','refund')) NOT NULL,
    covers_full_year BOOLEAN DEFAULT 0,   -- true only for active members paying $220
    needs_review BOOLEAN DEFAULT 0,       -- true if tolerance-matched or otherwise flagged
    source_text TEXT,          -- original raw transaction text, for audit trail
    match_confidence REAL,     -- fuzzy-match score, 0-1
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dues_status (
    id INTEGER PRIMARY KEY,
    member_id TEXT NOT NULL REFERENCES members(ut_id),
    semester TEXT NOT NULL,
    amount_owed REAL NOT NULL,
    amount_paid REAL DEFAULT 0,     -- only sums payments where payment_type = 'dues'
    last_reminder_sent TEXT,
    UNIQUE(member_id, semester)     -- one row per member per semester, not one row per member ever
);

CREATE TABLE IF NOT EXISTS parse_log (
    id INTEGER PRIMARY KEY,
    raw_input TEXT NOT NULL,
    parsed_output TEXT,        -- JSON string of what Claude returned
    status TEXT CHECK(status IN ('success','failed','low_confidence')),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS email_log (
    id INTEGER PRIMARY KEY,
    member_id TEXT REFERENCES members(ut_id),
    email_type TEXT CHECK(email_type IN ('donation_thanks','dues_confirmation','dues_reminder')) NOT NULL,
    recipient_email TEXT,
    content TEXT,
    sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
    mode TEXT CHECK(mode IN ('review','live')) NOT NULL
);

-- Configurable dues rates. Previously hardcoded in config.py — moving them
-- here means next year's treasurer can update rates without touching code.
CREATE TABLE IF NOT EXISTS dues_rates (
    status TEXT PRIMARY KEY CHECK(status IN ('pledge','active')),
    semester_amount REAL NOT NULL,
    year_amount REAL,          -- NULL for pledge — pledges may not pay per-year (Section 4.5)
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Default rates. INSERT OR IGNORE so re-running this script never clobbers a
-- treasurer's manual rate change — the primary-key conflict makes this a
-- no-op after the first run.
INSERT OR IGNORE INTO dues_rates (status, semester_amount, year_amount) VALUES ('pledge', 150.0, NULL);
INSERT OR IGNORE INTO dues_rates (status, semester_amount, year_amount) VALUES ('active', 130.0, 220.0);
