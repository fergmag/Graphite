import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional, Tuple

DB_PATH = os.environ.get("GRAPHITE_DB_PATH", "graphite.db")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS comps (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              query TEXT NOT NULL,
              title TEXT,
              price REAL NOT NULL,
              url TEXT,
              ended TEXT,
              created_at TEXT DEFAULT (datetime('now'))
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS estimates (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              query TEXT NOT NULL,
              n INTEGER NOT NULL,
              median REAL,
              trimmed_mean REAL,
              p25 REAL,
              p75 REAL,
              min_price REAL,
              max_price REAL,
              confidence REAL NOT NULL,
              created_at TEXT DEFAULT (datetime('now'))
            );
            """
        )


def insert_comps(query: str, comps: List[Dict[str, Any]]) -> int:
    rows = 0
    with get_conn() as conn:
        for c in comps:
            price = c.get("price")
            if price is None:
                continue
            conn.execute(
                """
                INSERT INTO comps (query, title, price, url, ended)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    query,
                    c.get("title"),
                    float(price),
                    c.get("url"),
                    c.get("ended"),
                ),
            )
            rows += 1
    return rows


def insert_estimate(query: str, summary: Dict[str, Any]) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO estimates (query, n, median, trimmed_mean, p25, p75, min_price, max_price, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                query,
                int(summary.get("n", 0)),
                summary.get("median"),
                summary.get("trimmed_mean"),
                summary.get("p25"),
                summary.get("p75"),
                summary.get("min_price"),
                summary.get("max_price"),
                float(summary.get("confidence", 0.0)),
            ),
        )


def latest_estimate(query: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT query, n, median, trimmed_mean, p25, p75, min_price, max_price, confidence, created_at
            FROM estimates
            WHERE query = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (query,),
        ).fetchone()
        if not row:
            return None
        return dict(row)
