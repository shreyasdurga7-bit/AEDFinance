"""Section 5.3 — Gemini parsing layer.

Turns one raw transaction row (arbitrary Venmo/Zelle CSV text) into structured
fields via the Gemini API. Never guesses: Gemini is instructed to return null
for anything it can't confidently extract, and every attempt (success or
failure) is logged to parse_log for audit purposes. A single bad row must
never halt the batch.
"""
import json
import sqlite3
import time
from dataclasses import dataclass

from google import genai
from google.genai import types as genai_types

from dues_automation import config

SYSTEM_PROMPT = """You extract structured payment info from a single raw transaction row \
exported from a payment app (Venmo or Zelle/bank CSV).

Return ONLY valid JSON, no prose, no markdown code fences. The JSON object must have \
exactly these keys: "name", "amount", "date", "note".

- "name": the human name of the person who SENT the payment (not the recipient), as a \
string, or null if you cannot confidently determine it.
- "amount": the payment amount as a plain number (no currency symbols, no commas), or \
null if you cannot confidently determine it.
- "date": the transaction date as a string in YYYY-MM-DD format if determinable, else null.
- "note": the memo/description text if present, else null.

Never guess. If a field cannot be confidently extracted from the input, return null for \
that field rather than a best-effort guess."""


@dataclass
class ParseResult:
    status: str  # 'success' or 'failed'
    parsed: dict | None
    error: str | None = None


def extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def parse_transaction_row(raw_text: str, client: genai.Client) -> ParseResult:
    try:
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=raw_text,
            config=genai_types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=300,
            ),
        )
        parsed = extract_json(response.text)
        required_keys = {"name", "amount", "date", "note"}
        if not required_keys.issubset(parsed.keys()):
            return ParseResult(status="failed", parsed=None, error=f"missing keys in {parsed!r}")
        return ParseResult(status="success", parsed=parsed)
    except Exception as exc:  # noqa: BLE001 — one bad row must never halt the batch
        return ParseResult(status="failed", parsed=None, error=str(exc))


def _log_parse(conn: sqlite3.Connection, raw_text: str, result: ParseResult) -> None:
    conn.execute(
        "INSERT INTO parse_log (raw_input, parsed_output, status) VALUES (?, ?, ?)",
        (
            raw_text,
            json.dumps(result.parsed) if result.parsed is not None else result.error,
            result.status,
        ),
    )


def parse_batch(
    raw_rows: list[str],
    conn: sqlite3.Connection,
    client: genai.Client | None = None,
    delay_seconds: float = 0.2,
) -> list[ParseResult]:
    """Parse each raw row via Gemini, logging every attempt to parse_log.

    Relies on the google-genai SDK's built-in retry/backoff for transient
    errors; any row that still fails is logged and skipped rather than
    halting the run.
    """
    client = client or genai.Client(api_key=config.GEMINI_API_KEY)
    results = []
    for raw_text in raw_rows:
        result = parse_transaction_row(raw_text, client)
        _log_parse(conn, raw_text, result)
        results.append(result)
        if delay_seconds:
            time.sleep(delay_seconds)
    conn.commit()
    return results
