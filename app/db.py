import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

DB_PATH = os.environ.get("GRAPHITE_DB", "graphite.db")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _columns(con: sqlite3.Connection, table: str) -> List[str]:
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    return [r["name"] for r in rows]


def _ensure_column(con: sqlite3.Connection, table: str, col: str, coltype: str) -> None:
    cols = _columns(con, table)
    if col in cols:
        return
    con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")


def init_db() -> None:
    """
    Creates tables if missing and performs lightweight migrations (ADD COLUMN)
    so older local DBs don't crash when schema changes.
    """
    con = _connect()
    try:
        # comps
        if not _table_exists(con, "comps"):
            con.execute(
                """
                CREATE TABLE comps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    title TEXT,
                    price REAL,
                    shipping REAL,
                    url TEXT,
                    ended TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
        else:
            # migrations for older DBs
            _ensure_column(con, "comps", "shipping", "REAL")
            _ensure_column(con, "comps", "ended", "TEXT")
            _ensure_column(con, "comps", "url", "TEXT")
            _ensure_column(con, "comps", "created_at", "TEXT")

        # estimates
        if not _table_exists(con, "estimates"):
            con.execute(
                """
                CREATE TABLE estimates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    casp REAL,
                    accuracy_pct INTEGER,
                    confidence REAL,
                    public_json TEXT,
                    summary_json TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
        else:
            _ensure_column(con, "estimates", "casp", "REAL")
            _ensure_column(con, "estimates", "accuracy_pct", "INTEGER")
            _ensure_column(con, "estimates", "confidence", "REAL")
            _ensure_column(con, "estimates", "public_json", "TEXT")
            _ensure_column(con, "estimates", "summary_json", "TEXT")
            _ensure_column(con, "estimates", "created_at", "TEXT")

        # watchlist
        if not _table_exists(con, "watchlist"):
            con.execute(
                """
                CREATE TABLE watchlist (
                    query TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL
                )
                """
            )

        con.commit()
    finally:
        con.close()


def insert_comps(query: str, comps: List[Dict[str, Any]]) -> int:
    """
    Inserts comps; returns number inserted.
    Expects each comp dict may include: title, price, shipping, url, ended.
    """
    if not comps:
        return 0

    now = _utc_now()
    rows: List[Tuple[Any, ...]] = []
    for c in comps:
        rows.append(
            (
                query,
                c.get("title"),
                c.get("price"),
                c.get("shipping"),
                c.get("url"),
                c.get("ended"),
                now,
            )
        )

    con = _connect()
    try:
        cur = con.cursor()
        cur.executemany(
            """
            INSERT INTO comps (query, title, price, shipping, url, ended, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        con.commit()
        return cur.rowcount if cur.rowcount is not None else len(rows)
    finally:
        con.close()


def insert_estimate(query: str, public_payload: Dict[str, Any], summary_payload: Dict[str, Any]) -> None:
    now = _utc_now()
    casp = public_payload.get("casp")
    accuracy_pct = public_payload.get("accuracy_pct")
    confidence = public_payload.get("confidence_raw")

    con = _connect()
    try:
        con.execute(
            """
            INSERT INTO estimates (query, casp, accuracy_pct, confidence, public_json, summary_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                query,
                casp,
                accuracy_pct,
                confidence,
                json.dumps(public_payload, ensure_ascii=False),
                json.dumps(summary_payload, ensure_ascii=False),
                now,
            ),
        )
        con.commit()
    finally:
        con.close()


# -----------------------------
# Watchlist helpers
# -----------------------------

def list_watches() -> List[str]:
    con = _connect()
    try:
        rows = con.execute(
            "SELECT query FROM watchlist ORDER BY created_at DESC"
        ).fetchall()
        return [r["query"] for r in rows]
    finally:
        con.close()


def add_watch(query: str) -> None:
    if query is None:
        return
    if not isinstance(query, str):
        query = str(query)
    if not query.strip():
        return
    con = _connect()
    try:
        con.execute(
            "INSERT OR IGNORE INTO watchlist (query, created_at) VALUES (?, ?)",
            (query, _utc_now()),
        )
        con.commit()
    finally:
        con.close()


def delete_watch(query: str) -> None:
    if query is None:
        return
    if not isinstance(query, str):
        query = str(query)
    if not query.strip():
        return
    con = _connect()
    try:
        con.execute("DELETE FROM watchlist WHERE query=?", (query,))
        con.commit()
    finally:
        con.close()
