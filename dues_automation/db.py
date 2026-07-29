"""Shared SQLite connection helper."""
import sqlite3
from pathlib import Path

from dues_automation import config


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables from schema.sql if they don't already exist."""
    schema_path = Path(__file__).resolve().parent / "schema.sql"
    with get_connection() as conn:
        conn.executescript(schema_path.read_text())
