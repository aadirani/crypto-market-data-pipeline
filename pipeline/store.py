"""Load: write candles into SQLite idempotently, and run named SQL queries."""

import math
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # SQLite has no built-in square root everywhere; register Python's so SQL can compute volatility.
    conn.create_function("sqrt", 1, lambda x: math.sqrt(x) if x is not None and x >= 0 else None)
    conn.executescript((SQL_DIR / "schema.sql").read_text(encoding="utf-8"))
    return conn


def upsert_candles(conn, symbol, interval, candles, source):
    """Insert new candles and update existing ones. Running twice gives the same result."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = [(symbol, interval, c["open_time"], c["open"], c["high"], c["low"], c["close"],
             c["volume"], c["turnover"], now) for c in candles]
    with conn:  # one transaction: all rows or none
        conn.executemany(
            """
            INSERT INTO candles (symbol, interval, open_time, open, high, low, close,
                                 volume, turnover, ingested_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (symbol, interval, open_time) DO UPDATE SET
                open = excluded.open, high = excluded.high, low = excluded.low,
                close = excluded.close, volume = excluded.volume,
                turnover = excluded.turnover, ingested_at = excluded.ingested_at
            """,
            rows,
        )
        conn.execute(
            "INSERT INTO ingestion_runs (run_at, source, symbol, interval, rows_received) "
            "VALUES (?, ?, ?, ?, ?)",
            (now, source, symbol, interval, len(rows)),
        )
    return len(rows)


def load_queries(path=SQL_DIR / "analytics.sql"):
    """Split a .sql file into {name: query} using '-- name: <name>' markers."""
    text = Path(path).read_text(encoding="utf-8")
    parts = re.split(r"^-- name: (\w+)\s*$", text, flags=re.MULTILINE)
    return {name: sql.strip() for name, sql in zip(parts[1::2], parts[2::2])}


def run_query(conn, sql, **params):
    return [dict(row) for row in conn.execute(sql, params)]
