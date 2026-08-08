# -*- coding: utf-8 -*-
"""SQLite store for fesbuk dashboard: pending/scheduled posts.
DB file: <repo>/fesbuk.db (gitignored).
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

try:
    from fesbuk import config
except ImportError:
    import config

# DB file lives in <repo>/database/ (folder gitignored via *.db)
DB_DIR = config.ROOT / "database"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "fesbuk.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_file TEXT UNIQUE,            -- ref/label (content lives in `text`)
    text TEXT,
    status TEXT DEFAULT 'pending',   -- pending | posted
    created_at TEXT,
    scheduled_at TEXT,
    posted_at TEXT,
    fb_post_id TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def _migrate(conn):
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(posts)")]
    if "created_at" not in cols:
        conn.execute("ALTER TABLE posts ADD COLUMN created_at TEXT")
    if "page_id" not in cols:
        conn.execute("ALTER TABLE posts ADD COLUMN page_id TEXT")
    # backfill created_at for old rows
    conn.execute(
        "UPDATE posts SET created_at=COALESCE(posted_at, created_at) "
        "WHERE created_at IS NULL OR created_at=''"
    )
    conn.execute(
        "UPDATE posts SET created_at=datetime('now') WHERE created_at IS NULL OR created_at=''"
    )
    conn.commit()


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _conn()
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.close()


def seed_from_msgs():
    """Add any msg file in knowledge/msgs/ that is not yet in the DB (status pending)."""
    msgs_dir = config.ROOT / "knowledge" / "msgs"
    init_db()
    conn = _conn()
    existing = {r["msg_file"] for r in conn.execute("SELECT msg_file FROM posts")}
    for f in sorted(msgs_dir.glob("*.txt")):
        if f.name not in existing:
            conn.execute(
                "INSERT INTO posts (msg_file, text, created_at) VALUES (?, ?, ?)",
                (f.name, f.read_text(encoding="utf-8").strip()[:2000],
                 datetime.now(timezone.utc).isoformat()),
            )
    conn.commit()
    conn.close()


def mark_posted(msg_file: str, fb_post_id: str):
    conn = _conn()
    conn.execute(
        "UPDATE posts SET status='posted', posted_at=?, fb_post_id=? WHERE msg_file=?",
        (datetime.now(timezone.utc).isoformat(), fb_post_id, msg_file),
    )
    conn.commit()
    conn.close()


def mark_posted_by_id(pid: int, fb_post_id: str):
    conn = _conn()
    conn.execute(
        "UPDATE posts SET status='posted', posted_at=?, fb_post_id=? WHERE id=?",
        (datetime.now(timezone.utc).isoformat(), fb_post_id, pid),
    )
    conn.commit()
    conn.close()


def get_post_by_id(pid: int):
    conn = _conn()
    row = conn.execute("SELECT * FROM posts WHERE id=?", (pid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_post_by_file(msg_file: str):
    conn = _conn()
    row = conn.execute("SELECT * FROM posts WHERE msg_file=?", (msg_file,)).fetchone()
    conn.close()
    return dict(row) if row else None


def search_posts(q=None, page=1, per_page=10):
    """Search + paginate posts. Returns (rows, total)."""
    conn = _conn()
    where, params = "", []
    if q:
        where = "WHERE text LIKE ? OR msg_file LIKE ?"
        params = [f"%{q}%", f"%{q}%"]
    total = conn.execute(f"SELECT COUNT(*) FROM posts {where}", params).fetchone()[0]
    offset = (page - 1) * per_page
    rows = conn.execute(
        f"SELECT * FROM posts {where} ORDER BY id DESC LIMIT ? OFFSET ?",
        params + [per_page, offset],
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows], total


def create_post(text: str, image: str = None, page_id: str = None, scheduled_at: str = None) -> int:
    """Insert a new post. Returns row id."""
    conn = _conn()
    cur = conn.execute(
        "INSERT INTO posts (msg_file, text, image, page_id, status, created_at, scheduled_at) "
        "VALUES (?, ?, ?, ?, 'pending', ?, ?)",
        (f"manual_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}", text, image, page_id,
         datetime.now(timezone.utc).isoformat(), scheduled_at),
    )
    conn.commit()
    conn.close()
    return cur.lastrowid


def update_post(pid: int, text: str, image: str = None, page_id: str = None,
                scheduled_at: str = None, status: str = None) -> bool:
    """Update a post's content/plan. Returns True if the row existed."""
    conn = _conn()
    row = conn.execute("SELECT id FROM posts WHERE id=?", (pid,)).fetchone()
    if not row:
        conn.close()
        return False
    fields, params = ["text=?", "image=?", "page_id=?", "scheduled_at=?"], [text, image, page_id, scheduled_at]
    if status is not None:
        fields.append("status=?")
        params.append(status)
    params.append(pid)
    conn.execute(f"UPDATE posts SET {', '.join(fields)} WHERE id=?", params)
    conn.commit()
    conn.close()
    return True


def delete_post(pid: int) -> bool:
    """Delete a post row. Returns True if it existed. Does NOT touch the FB post."""
    conn = _conn()
    cur = conn.execute("DELETE FROM posts WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def get_due_posts(now_iso: str) -> list:
    """Scheduled posts that are due (scheduled_at <= now) and still pending."""
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM posts WHERE status='pending' AND scheduled_at IS NOT NULL "
        "AND scheduled_at <= ? ORDER BY scheduled_at",
        (now_iso,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------- settings (hidden pages etc.) ----------

def get_setting(key: str, default=None):
    conn = _conn()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    conn = _conn()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


def hidden_pages() -> list:
    import json
    raw = get_setting("hidden_pages", "[]")
    try:
        return json.loads(raw)
    except Exception:
        return []


def toggle_hidden_page(page_id: str) -> bool:
    """Toggle page visibility. Returns True if now hidden."""
    import json
    hidden = set(hidden_pages())
    if page_id in hidden:
        hidden.discard(page_id)
        now_hidden = False
    else:
        hidden.add(page_id)
        now_hidden = True
    set_setting("hidden_pages", json.dumps(sorted(hidden)))
    return now_hidden


def get_posts(status=None):
    conn = _conn()
    if status:
        rows = conn.execute("SELECT * FROM posts WHERE status=? ORDER BY id", (status,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM posts ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]
