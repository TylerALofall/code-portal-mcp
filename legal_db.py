"""
Legal Document Database Layer
==============================
SQLite-backed storage for legal document templates, fact blocks,
defendant information, stored files, and built document packages.

Supports up to 2000 templates for ORS (Oregon state court) and
Federal (District of Oregon) court systems.
"""

import sqlite3
import json
import os
import datetime
from typing import Dict, List, Optional, Any, Tuple

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "legal_data.db")
FILES_DIR = os.path.join(BASE_DIR, "legal_files")
os.makedirs(FILES_DIR, exist_ok=True)

MAX_TEMPLATES = 2000

# ── Connection helper ──────────────────────────────────────────────────────────
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


# ── Schema creation ────────────────────────────────────────────────────────────
def init_db():
    """Create all tables if they do not already exist."""
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS templates (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            category    TEXT    NOT NULL DEFAULT 'ORS',   -- 'ORS' | 'Federal'
            court_type  TEXT    NOT NULL DEFAULT '',       -- e.g. 'Multnomah County Circuit Court'
            description TEXT    NOT NULL DEFAULT '',
            content_blocks TEXT NOT NULL DEFAULT '[]',    -- JSON array of block objects
            tags        TEXT    NOT NULL DEFAULT '[]',     -- JSON array of strings
            created_at  TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS fact_blocks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT    NOT NULL,
            content     TEXT    NOT NULL,
            category    TEXT    NOT NULL DEFAULT '',
            tags        TEXT    NOT NULL DEFAULT '[]',
            source      TEXT    NOT NULL DEFAULT '',
            created_at  TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS defendants (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            case_number TEXT    NOT NULL DEFAULT '',
            court       TEXT    NOT NULL DEFAULT '',
            charges     TEXT    NOT NULL DEFAULT '[]',    -- JSON array
            address     TEXT    NOT NULL DEFAULT '',
            dob         TEXT    NOT NULL DEFAULT '',
            phone       TEXT    NOT NULL DEFAULT '',
            notes       TEXT    NOT NULL DEFAULT '',
            extra_info  TEXT    NOT NULL DEFAULT '{}',   -- JSON object for any other fields
            created_at  TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS stored_files (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            original_filename TEXT    NOT NULL,
            stored_filename   TEXT    NOT NULL UNIQUE,
            file_type         TEXT    NOT NULL DEFAULT '',
            description       TEXT    NOT NULL DEFAULT '',
            category          TEXT    NOT NULL DEFAULT '',
            file_size         INTEGER NOT NULL DEFAULT 0,
            created_at        TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS document_packages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT    NOT NULL,
            defendant_id    INTEGER,
            template_id     INTEGER,
            fact_block_ids  TEXT    NOT NULL DEFAULT '[]',   -- JSON array of fact_block ids
            output_content  TEXT    NOT NULL DEFAULT '',
            created_at      TEXT    NOT NULL,
            FOREIGN KEY (defendant_id) REFERENCES defendants(id) ON DELETE SET NULL,
            FOREIGN KEY (template_id)  REFERENCES templates(id)  ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS research_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            query       TEXT    NOT NULL,
            providers   TEXT    NOT NULL DEFAULT '[]',    -- JSON array of providers queried
            results     TEXT    NOT NULL DEFAULT '{}',   -- JSON object: provider -> result
            created_at  TEXT    NOT NULL
        );
        """)
    print("✅ Legal database initialized")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ══════════════════════════════════════════════════════════════════════════════
# Templates
# ══════════════════════════════════════════════════════════════════════════════

def template_count() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) FROM templates").fetchone()
        return row[0]


def create_template(
    name: str,
    category: str = "ORS",
    court_type: str = "",
    description: str = "",
    content_blocks: List[Dict] = None,
    tags: List[str] = None,
) -> Dict:
    if template_count() >= MAX_TEMPLATES:
        raise ValueError(f"Template limit of {MAX_TEMPLATES} reached.")
    now = _now()
    blocks_json = json.dumps(content_blocks or [])
    tags_json = json.dumps(tags or [])
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO templates (name, category, court_type, description,
               content_blocks, tags, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (name, category, court_type, description, blocks_json, tags_json, now, now),
        )
        return get_template(cur.lastrowid)


def get_template(template_id: int) -> Optional[Dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM templates WHERE id=?", (template_id,)).fetchone()
        return _template_row(row) if row else None


def list_templates(
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict]:
    query = "SELECT * FROM templates WHERE 1=1"
    params: List[Any] = []
    if category:
        query += " AND category=?"
        params.append(category)
    if search:
        query += " AND (name LIKE ? OR description LIKE ? OR tags LIKE ?)"
        s = f"%{search}%"
        params.extend([s, s, s])
    query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [_template_row(r) for r in rows]


def update_template(template_id: int, **fields) -> Optional[Dict]:
    allowed = {"name", "category", "court_type", "description", "content_blocks", "tags"}
    updates = {}
    for k, v in fields.items():
        if k in allowed and v is not None:
            if k in ("content_blocks", "tags"):
                updates[k] = json.dumps(v)
            else:
                updates[k] = v
    if not updates:
        return get_template(template_id)
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [template_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE templates SET {set_clause} WHERE id=?", values)
    return get_template(template_id)


def delete_template(template_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM templates WHERE id=?", (template_id,))
        return cur.rowcount > 0


def _template_row(row: sqlite3.Row) -> Dict:
    d = dict(row)
    d["content_blocks"] = json.loads(d.get("content_blocks") or "[]")
    d["tags"] = json.loads(d.get("tags") or "[]")
    return d


# ══════════════════════════════════════════════════════════════════════════════
# Fact Blocks
# ══════════════════════════════════════════════════════════════════════════════

def create_fact_block(
    title: str,
    content: str,
    category: str = "",
    tags: List[str] = None,
    source: str = "",
) -> Dict:
    now = _now()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO fact_blocks (title, content, category, tags, source, created_at)
               VALUES (?,?,?,?,?,?)""",
            (title, content, category, json.dumps(tags or []), source, now),
        )
        return get_fact_block(cur.lastrowid)


def get_fact_block(fact_id: int) -> Optional[Dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM fact_blocks WHERE id=?", (fact_id,)).fetchone()
        return _fact_row(row) if row else None


def list_fact_blocks(
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict]:
    query = "SELECT * FROM fact_blocks WHERE 1=1"
    params: List[Any] = []
    if category:
        query += " AND category=?"
        params.append(category)
    if search:
        query += " AND (title LIKE ? OR content LIKE ? OR tags LIKE ?)"
        s = f"%{search}%"
        params.extend([s, s, s])
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [_fact_row(r) for r in rows]


def update_fact_block(fact_id: int, **fields) -> Optional[Dict]:
    allowed = {"title", "content", "category", "tags", "source"}
    updates = {}
    for k, v in fields.items():
        if k in allowed and v is not None:
            updates[k] = json.dumps(v) if k == "tags" else v
    if not updates:
        return get_fact_block(fact_id)
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [fact_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE fact_blocks SET {set_clause} WHERE id=?", values)
    return get_fact_block(fact_id)


def delete_fact_block(fact_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM fact_blocks WHERE id=?", (fact_id,))
        return cur.rowcount > 0


def _fact_row(row: sqlite3.Row) -> Dict:
    d = dict(row)
    d["tags"] = json.loads(d.get("tags") or "[]")
    return d


# ══════════════════════════════════════════════════════════════════════════════
# Defendants
# ══════════════════════════════════════════════════════════════════════════════

def create_defendant(
    name: str,
    case_number: str = "",
    court: str = "",
    charges: List[str] = None,
    address: str = "",
    dob: str = "",
    phone: str = "",
    notes: str = "",
    extra_info: Dict = None,
) -> Dict:
    now = _now()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO defendants
               (name, case_number, court, charges, address, dob, phone, notes, extra_info, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                name, case_number, court,
                json.dumps(charges or []),
                address, dob, phone, notes,
                json.dumps(extra_info or {}),
                now,
            ),
        )
        return get_defendant(cur.lastrowid)


def get_defendant(def_id: int) -> Optional[Dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM defendants WHERE id=?", (def_id,)).fetchone()
        return _defendant_row(row) if row else None


def list_defendants(search: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[Dict]:
    query = "SELECT * FROM defendants WHERE 1=1"
    params: List[Any] = []
    if search:
        query += " AND (name LIKE ? OR case_number LIKE ? OR court LIKE ?)"
        s = f"%{search}%"
        params.extend([s, s, s])
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [_defendant_row(r) for r in rows]


def update_defendant(def_id: int, **fields) -> Optional[Dict]:
    allowed = {"name", "case_number", "court", "charges", "address", "dob", "phone", "notes", "extra_info"}
    updates = {}
    for k, v in fields.items():
        if k in allowed and v is not None:
            updates[k] = json.dumps(v) if k in ("charges", "extra_info") else v
    if not updates:
        return get_defendant(def_id)
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [def_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE defendants SET {set_clause} WHERE id=?", values)
    return get_defendant(def_id)


def delete_defendant(def_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM defendants WHERE id=?", (def_id,))
        return cur.rowcount > 0


def _defendant_row(row: sqlite3.Row) -> Dict:
    d = dict(row)
    d["charges"] = json.loads(d.get("charges") or "[]")
    d["extra_info"] = json.loads(d.get("extra_info") or "{}")
    return d


# ══════════════════════════════════════════════════════════════════════════════
# Stored Files
# ══════════════════════════════════════════════════════════════════════════════

def create_stored_file(
    original_filename: str,
    stored_filename: str,
    file_type: str = "",
    description: str = "",
    category: str = "",
    file_size: int = 0,
) -> Dict:
    now = _now()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO stored_files
               (original_filename, stored_filename, file_type, description, category, file_size, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (original_filename, stored_filename, file_type, description, category, file_size, now),
        )
        return get_stored_file(cur.lastrowid)


def get_stored_file(file_id: int) -> Optional[Dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM stored_files WHERE id=?", (file_id,)).fetchone()
        return dict(row) if row else None


def list_stored_files(
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict]:
    query = "SELECT * FROM stored_files WHERE 1=1"
    params: List[Any] = []
    if category:
        query += " AND category=?"
        params.append(category)
    if search:
        query += " AND (original_filename LIKE ? OR description LIKE ?)"
        s = f"%{search}%"
        params.extend([s, s])
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def delete_stored_file(file_id: int) -> Tuple[bool, str]:
    """Delete the DB record and the physical file. Returns (success, stored_filename)."""
    rec = get_stored_file(file_id)
    if not rec:
        return False, ""
    path = os.path.join(FILES_DIR, rec["stored_filename"])
    if os.path.exists(path):
        os.remove(path)
    with get_conn() as conn:
        conn.execute("DELETE FROM stored_files WHERE id=?", (file_id,))
    return True, rec["stored_filename"]


# ══════════════════════════════════════════════════════════════════════════════
# Document Packages
# ══════════════════════════════════════════════════════════════════════════════

def create_document_package(
    name: str,
    output_content: str,
    defendant_id: Optional[int] = None,
    template_id: Optional[int] = None,
    fact_block_ids: List[int] = None,
) -> Dict:
    now = _now()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO document_packages
               (name, defendant_id, template_id, fact_block_ids, output_content, created_at)
               VALUES (?,?,?,?,?,?)""",
            (name, defendant_id, template_id, json.dumps(fact_block_ids or []), output_content, now),
        )
        return get_document_package(cur.lastrowid)


def get_document_package(pkg_id: int) -> Optional[Dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM document_packages WHERE id=?", (pkg_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["fact_block_ids"] = json.loads(d.get("fact_block_ids") or "[]")
        return d


def list_document_packages(limit: int = 50, offset: int = 0) -> List[Dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM document_packages ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["fact_block_ids"] = json.loads(d.get("fact_block_ids") or "[]")
            result.append(d)
        return result


def delete_document_package(pkg_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM document_packages WHERE id=?", (pkg_id,))
        return cur.rowcount > 0


# ══════════════════════════════════════════════════════════════════════════════
# Research History
# ══════════════════════════════════════════════════════════════════════════════

def save_research(query: str, providers: List[str], results: Dict) -> Dict:
    now = _now()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO research_history (query, providers, results, created_at)
               VALUES (?,?,?,?)""",
            (query, json.dumps(providers), json.dumps(results), now),
        )
        row = conn.execute(
            "SELECT * FROM research_history WHERE id=?", (cur.lastrowid,)
        ).fetchone()
        d = dict(row)
        d["providers"] = json.loads(d.get("providers") or "[]")
        d["results"] = json.loads(d.get("results") or "{}")
        return d


def list_research_history(limit: int = 50, offset: int = 0) -> List[Dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, query, providers, created_at FROM research_history "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["providers"] = json.loads(d.get("providers") or "[]")
            result.append(d)
        return result


def get_research(research_id: int) -> Optional[Dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM research_history WHERE id=?", (research_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["providers"] = json.loads(d.get("providers") or "[]")
        d["results"] = json.loads(d.get("results") or "{}")
        return d


# ── Auto-init ──────────────────────────────────────────────────────────────────
init_db()
