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


_APP_DIR = os.path.dirname(os.path.abspath(__file__))


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
                    currency TEXT,
                    url TEXT,
                    ended TEXT,
                    ended_at TEXT,
                    source TEXT,
                    model_guess TEXT,
                    listing_id TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
        else:
            # migrations for older DBs
            _ensure_column(con, "comps", "shipping", "REAL")
            _ensure_column(con, "comps", "currency", "TEXT")
            _ensure_column(con, "comps", "ended", "TEXT")
            _ensure_column(con, "comps", "ended_at", "TEXT")
            _ensure_column(con, "comps", "url", "TEXT")
            _ensure_column(con, "comps", "source", "TEXT")
            _ensure_column(con, "comps", "model_guess", "TEXT")
            _ensure_column(con, "comps", "listing_id", "TEXT")
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

        # listings
        listings_new = not _table_exists(con, "listings")
        if listings_new:
            con.execute(
                """
                CREATE TABLE listings (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    size TEXT,
                    price REAL,
                    description TEXT,
                    photos TEXT,
                    sold INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    position INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            # Migrate from listings.json if it exists
            _migrate_listings_json(con)

        # archive
        archive_new = not _table_exists(con, "archive_sections")
        if archive_new:
            con.execute(
                """
                CREATE TABLE archive_sections (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    position INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            con.execute(
                """
                CREATE TABLE archive_subsections (
                    id TEXT PRIMARY KEY,
                    section_id TEXT NOT NULL,
                    title TEXT,
                    text TEXT,
                    photos TEXT,
                    position INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            # Migrate from archive.json if it exists
            _migrate_archive_json(con)

        con.commit()
    finally:
        con.close()


def _migrate_listings_json(con: sqlite3.Connection) -> None:
    path = os.path.join(_APP_DIR, "listings.json")
    try:
        with open(path) as f:
            listings = json.load(f)
    except Exception:
        return
    for i, l in enumerate(listings):
        con.execute(
            "INSERT OR IGNORE INTO listings (id, title, size, price, description, photos, sold, created_at, position) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                str(l.get("id", "")),
                l.get("title", ""),
                l.get("size", ""),
                l.get("price"),
                l.get("description", ""),
                json.dumps(l.get("photos") or []),
                1 if l.get("sold") else 0,
                l.get("created_at", _utc_now()),
                i,
            ),
        )


def _migrate_archive_json(con: sqlite3.Connection) -> None:
    path = os.path.join(_APP_DIR, "archive.json")
    try:
        with open(path) as f:
            sections = json.load(f)
    except Exception:
        return
    for si, section in enumerate(sections):
        con.execute(
            "INSERT OR IGNORE INTO archive_sections (id, title, position) VALUES (?,?,?)",
            (section["id"], section["title"], si),
        )
        for ssi, sub in enumerate(section.get("subsections") or []):
            con.execute(
                "INSERT OR IGNORE INTO archive_subsections (id, section_id, title, text, photos, position) VALUES (?,?,?,?,?,?)",
                (
                    sub["id"],
                    section["id"],
                    sub.get("title", ""),
                    sub.get("text", ""),
                    json.dumps(sub.get("photos") or []),
                    ssi,
                ),
            )


def insert_comps(query: str, comps: List[Dict[str, Any]]) -> int:
    """
    Inserts comps; returns number inserted.
    Expects each comp dict may include:
    title, price, shipping, currency, url, ended, ended_at, source, model_guess, listing_id.
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
                c.get("currency"),
                c.get("url"),
                c.get("ended"),
                c.get("ended_at"),
                c.get("source"),
                c.get("model_guess"),
                c.get("listing_id"),
                now,
            )
        )

    con = _connect()
    try:
        cur = con.cursor()
        cur.executemany(
            """
            INSERT INTO comps (
                query,
                title,
                price,
                shipping,
                currency,
                url,
                ended,
                ended_at,
                source,
                model_guess,
                listing_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def list_comps(limit: int = 100) -> List[Dict[str, Any]]:
    con = _connect()
    try:
        rows = con.execute(
            """
            SELECT query, title, price, url, ended_at, source, created_at
            FROM comps
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def count_comps() -> int:
    con = _connect()
    try:
        row = con.execute("SELECT COUNT(*) as n FROM comps").fetchone()
        return row["n"] if row else 0
    finally:
        con.close()


def count_comps_for_queries(normalized_queries: List[str]) -> Dict[str, int]:
    """Returns {normalized_query: count} for each query that has comps in the DB."""
    if not normalized_queries:
        return {}
    con = _connect()
    try:
        placeholders = ",".join("?" * len(normalized_queries))
        rows = con.execute(
            f"SELECT query, COUNT(*) as n FROM comps WHERE query IN ({placeholders}) GROUP BY query",
            normalized_queries,
        ).fetchall()
        return {r["query"]: r["n"] for r in rows}
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


# -----------------------------
# Listings helpers
# -----------------------------

def _row_to_listing(r: sqlite3.Row) -> Dict[str, Any]:
    d = dict(r)
    try:
        d["photos"] = json.loads(d.get("photos") or "[]")
    except Exception:
        d["photos"] = []
    d["sold"] = bool(d.get("sold", 0))
    return d


def db_list_listings() -> List[Dict[str, Any]]:
    con = _connect()
    try:
        rows = con.execute(
            "SELECT * FROM listings ORDER BY position ASC, created_at DESC"
        ).fetchall()
        return [_row_to_listing(r) for r in rows]
    finally:
        con.close()


def db_insert_listing(listing: Dict[str, Any]) -> None:
    con = _connect()
    try:
        max_pos = con.execute("SELECT COALESCE(MIN(position)-1, 0) FROM listings").fetchone()[0]
        con.execute(
            "INSERT INTO listings (id, title, size, price, description, photos, sold, created_at, position) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                listing["id"],
                listing.get("title", ""),
                listing.get("size", ""),
                listing.get("price"),
                listing.get("description", ""),
                json.dumps(listing.get("photos") or []),
                1 if listing.get("sold") else 0,
                listing.get("created_at", _utc_now()),
                max_pos,
            ),
        )
        con.commit()
    finally:
        con.close()


def db_update_listing(listing_id: str, fields: Dict[str, Any]) -> None:
    con = _connect()
    try:
        row = con.execute("SELECT photos FROM listings WHERE id=?", (listing_id,)).fetchone()
        if not row:
            return
        existing_photos: List[str] = json.loads(row["photos"] or "[]")
        new_photos = fields.get("photos")
        if new_photos is not None:
            existing_photos.extend(new_photos)
        con.execute(
            """UPDATE listings SET title=?, size=?, price=?, description=?, photos=? WHERE id=?""",
            (
                fields.get("title"),
                fields.get("size"),
                fields.get("price"),
                fields.get("description", ""),
                json.dumps(existing_photos),
                listing_id,
            ),
        )
        con.commit()
    finally:
        con.close()


def db_toggle_sold(listing_id: str) -> None:
    con = _connect()
    try:
        con.execute(
            "UPDATE listings SET sold = CASE WHEN sold=1 THEN 0 ELSE 1 END WHERE id=?",
            (listing_id,),
        )
        con.commit()
    finally:
        con.close()


def db_delete_listing(listing_id: str) -> None:
    con = _connect()
    try:
        con.execute("DELETE FROM listings WHERE id=?", (listing_id,))
        con.commit()
    finally:
        con.close()


# -----------------------------
# Archive helpers
# -----------------------------

def db_load_archive() -> List[Dict[str, Any]]:
    con = _connect()
    try:
        sections = con.execute(
            "SELECT * FROM archive_sections ORDER BY position ASC"
        ).fetchall()
        result = []
        for s in sections:
            subs = con.execute(
                "SELECT * FROM archive_subsections WHERE section_id=? ORDER BY position ASC",
                (s["id"],),
            ).fetchall()
            sub_list = []
            for sub in subs:
                d = dict(sub)
                try:
                    d["photos"] = json.loads(d.get("photos") or "[]")
                except Exception:
                    d["photos"] = []
                sub_list.append(d)
            result.append({"id": s["id"], "title": s["title"], "subsections": sub_list})
        return result
    finally:
        con.close()


def db_add_section(section_id: str, title: str) -> None:
    con = _connect()
    try:
        max_pos = con.execute("SELECT COALESCE(MAX(position)+1, 0) FROM archive_sections").fetchone()[0]
        con.execute(
            "INSERT INTO archive_sections (id, title, position) VALUES (?,?,?)",
            (section_id, title, max_pos),
        )
        con.commit()
    finally:
        con.close()


def db_delete_section(section_id: str) -> None:
    con = _connect()
    try:
        con.execute("DELETE FROM archive_subsections WHERE section_id=?", (section_id,))
        con.execute("DELETE FROM archive_sections WHERE id=?", (section_id,))
        con.commit()
    finally:
        con.close()


def db_add_subsection(section_id: str, sub: Dict[str, Any]) -> None:
    con = _connect()
    try:
        max_pos = con.execute(
            "SELECT COALESCE(MAX(position)+1, 0) FROM archive_subsections WHERE section_id=?",
            (section_id,),
        ).fetchone()[0]
        con.execute(
            "INSERT INTO archive_subsections (id, section_id, title, text, photos, position) VALUES (?,?,?,?,?,?)",
            (
                sub["id"],
                section_id,
                sub.get("title", ""),
                sub.get("text", ""),
                json.dumps(sub.get("photos") or []),
                max_pos,
            ),
        )
        con.commit()
    finally:
        con.close()


def db_update_subsection(sub_id: str, fields: Dict[str, Any]) -> None:
    con = _connect()
    try:
        row = con.execute("SELECT photos FROM archive_subsections WHERE id=?", (sub_id,)).fetchone()
        if not row:
            return
        existing_photos: List[str] = json.loads(row["photos"] or "[]")
        new_photos = fields.get("photos")
        if new_photos:
            existing_photos.extend(new_photos)
        con.execute(
            "UPDATE archive_subsections SET title=?, text=?, photos=? WHERE id=?",
            (fields.get("title", ""), fields.get("text", ""), json.dumps(existing_photos), sub_id),
        )
        con.commit()
    finally:
        con.close()


def db_delete_subsection(sub_id: str) -> None:
    con = _connect()
    try:
        con.execute("DELETE FROM archive_subsections WHERE id=?", (sub_id,))
        con.commit()
    finally:
        con.close()
