import sqlite3
from pathlib import Path

DB_PATH = Path("data/inventory.db")


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS raw_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        source_object_id TEXT NOT NULL,
        name TEXT,
        display_name TEXT,
        enabled INTEGER,
        account_type TEXT,
        last_seen TEXT,
        raw_json TEXT NOT NULL,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(source, source_object_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS account_matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        left_source TEXT NOT NULL,
        left_object_id TEXT NOT NULL,
        right_source TEXT NOT NULL,
        right_object_id TEXT NOT NULL,
        confidence REAL NOT NULL,
        reason TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()