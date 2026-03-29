"""SQLite database management with WAL mode for concurrent access."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from config import DB_PATH

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS screenshots (
    id TEXT PRIMARY KEY,
    prnt_url TEXT NOT NULL,
    img_src TEXT,
    state TEXT NOT NULL DEFAULT 'discovered',
    local_filename TEXT,
    file_size_bytes INTEGER,
    image_hash TEXT,
    image_format TEXT,
    ocr_text TEXT,
    ocr_segments TEXT,  -- JSON array
    ocr_confidence REAL,
    filter_matched_pattern TEXT,
    discovered_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
    downloaded_at TIMESTAMP,
    ocr_processed_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
    claimed_by TEXT,
    claimed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_screenshots_state ON screenshots(state);
CREATE INDEX IF NOT EXISTS idx_screenshots_discovered ON screenshots(discovered_at);
CREATE INDEX IF NOT EXISTS idx_screenshots_hash ON screenshots(image_hash);
CREATE INDEX IF NOT EXISTS idx_screenshots_downloaded ON screenshots(downloaded_at);

CREATE VIRTUAL TABLE IF NOT EXISTS screenshots_fts USING fts5(
    id,
    ocr_text,
    content=screenshots,
    content_rowid=rowid
);

-- FTS sync triggers
CREATE TRIGGER IF NOT EXISTS fts_insert AFTER INSERT ON screenshots
WHEN new.ocr_text IS NOT NULL BEGIN
    INSERT INTO screenshots_fts(rowid, id, ocr_text)
    VALUES (new.rowid, new.id, new.ocr_text);
END;

CREATE TRIGGER IF NOT EXISTS fts_update AFTER UPDATE OF ocr_text ON screenshots
WHEN new.ocr_text IS NOT NULL BEGIN
    INSERT INTO screenshots_fts(screenshots_fts, rowid, id, ocr_text)
    VALUES ('delete', old.rowid, old.id, COALESCE(old.ocr_text, ''));
    INSERT INTO screenshots_fts(rowid, id, ocr_text)
    VALUES (new.rowid, new.id, new.ocr_text);
END;

CREATE TRIGGER IF NOT EXISTS fts_delete AFTER DELETE ON screenshots
WHEN old.ocr_text IS NOT NULL BEGIN
    INSERT INTO screenshots_fts(screenshots_fts, rowid, id, ocr_text)
    VALUES ('delete', old.rowid, old.id, old.ocr_text);
END;

CREATE TABLE IF NOT EXISTS proxies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    protocol TEXT NOT NULL,
    ip TEXT NOT NULL,
    port INTEGER NOT NULL,
    proxy_string TEXT NOT NULL,
    is_alive INTEGER DEFAULT 1,
    ssl_support INTEGER DEFAULT 0,
    last_success_at TIMESTAMP,
    last_failure_at TIMESTAMP,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    source TEXT,
    fetched_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
    UNIQUE(ip, port)
);

CREATE INDEX IF NOT EXISTS idx_proxies_alive ON proxies(is_alive);

CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
    last_login_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS blacklist_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL UNIQUE,
    added_by TEXT,
    added_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
    hit_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS image_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    screenshot_id TEXT NOT NULL REFERENCES screenshots(id),
    reason TEXT,
    reporter_ip TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
    resolved_at TIMESTAMP,
    resolved_by TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT
);
"""

# Default settings with descriptions
DEFAULT_SETTINGS = {
    "scraper_threads": ("5", "Number of scraper worker threads"),
    "scraper_id_min_length": ("2", "Minimum random ID length"),
    "scraper_id_max_length": ("7", "Maximum random ID length"),
    "scraper_delay": ("0.2", "Delay between scraper requests (seconds)"),
    "downloader_threads": ("5", "Number of downloader worker threads"),
    "downloader_use_proxy": ("true", "Route downloads through proxies"),
    "download_timeout": ("10", "Download request timeout (seconds)"),
    "min_image_size": ("1024", "Minimum image size in bytes"),
    "ocr_enabled": ("true", "Enable OCR text extraction"),
    "ocr_engine": ("doctr", "OCR engine: doctr or easyocr"),
    "ocr_gpu": ("false", "Use GPU for OCR"),
    "ocr_confidence_threshold": ("0.7", "Minimum OCR confidence (0.0-1.0)"),
    "ocr_languages": ("en", "OCR languages, comma-separated (easyocr only)"),
    "proxy_api_url": (
        "https://api.proxyscrape.com/v4/free-proxy-list/get"
        "?request=display_proxies&protocol=socks5,socks4"
        "&proxy_format=protocolipport&format=json&timeout=20000",
        "Proxy list API URL",
    ),
    "proxy_refresh_interval": ("3600", "Proxy refresh interval (seconds)"),
    "blocked_hosts": ("imageshack", "Blocked image hosts (comma-separated)"),
}


def _open_connection() -> sqlite3.Connection:
    """Open a new database connection."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    """Context manager for database operations with auto-commit. Opens and closes per use."""
    conn = _open_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create all tables and seed default settings. Safe to call multiple times."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        conn.executescript(SCHEMA)
        # Seed default settings
        for key, (value, description) in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value, description) VALUES (?, ?, ?)",
                (key, value, description),
            )
        conn.commit()
    finally:
        conn.close()


def get_setting(key: str) -> str | None:
    """Get a setting value by key."""
    with get_db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else DEFAULT_SETTINGS.get(key, (None,))[0]


def get_setting_int(key: str, default: int = 0) -> int:
    val = get_setting(key)
    try:
        return int(val) if val else default
    except ValueError:
        return default


def get_setting_float(key: str, default: float = 0.0) -> float:
    val = get_setting(key)
    try:
        return float(val) if val else default
    except ValueError:
        return default


def get_setting_bool(key: str, default: bool = False) -> bool:
    val = get_setting(key)
    if val is None:
        return default
    return val.lower() in ("true", "1", "yes")


def set_setting(key: str, value: str):
    """Set a setting value."""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?",
            (key, value, value),
        )


def get_all_settings() -> dict:
    """Get all settings as a dict with descriptions."""
    with get_db() as conn:
        rows = conn.execute("SELECT key, value, description FROM settings ORDER BY key").fetchall()
    return {r["key"]: {"value": r["value"], "description": r["description"]} for r in rows}


# Valid columns that transition() is allowed to update
_TRANSITION_COLUMNS = frozenset({
    "local_filename", "file_size_bytes", "image_hash", "image_format",
    "ocr_text", "ocr_segments", "ocr_confidence", "filter_matched_pattern",
    "downloaded_at", "ocr_processed_at", "img_src",
})

# Claims older than this are considered abandoned and can be reclaimed
CLAIM_TIMEOUT_SECONDS = 300  # 5 minutes


def claim_work(state: str, new_state: str, worker_id: str, limit: int = 1) -> list[str]:
    """Atomically claim rows for processing. Also reclaims stale claims."""
    with get_db() as conn:
        # First, recover any abandoned claims (older than timeout)
        conn.execute(
            """
            UPDATE screenshots
            SET state = ?, claimed_by = NULL, claimed_at = NULL
            WHERE state = ? AND claimed_by IS NOT NULL
              AND claimed_at < strftime('%Y-%m-%dT%H:%M:%f', 'now', ?)
            """,
            (state, new_state, f"-{CLAIM_TIMEOUT_SECONDS} seconds"),
        )

        cursor = conn.execute(
            """
            UPDATE screenshots
            SET state = ?, claimed_by = ?,
                claimed_at = strftime('%Y-%m-%dT%H:%M:%f', 'now'),
                updated_at = strftime('%Y-%m-%dT%H:%M:%f', 'now')
            WHERE id IN (
                SELECT id FROM screenshots
                WHERE state = ? AND claimed_by IS NULL
                ORDER BY discovered_at ASC
                LIMIT ?
            )
            RETURNING id
            """,
            (new_state, worker_id, state, limit),
        )
        return [row[0] for row in cursor.fetchall()]


def transition(screenshot_id: str, to_state: str, **kwargs):
    """Transition a screenshot to a new state with optional column updates."""
    sets = ["state = ?", "claimed_by = NULL", "claimed_at = NULL",
            "updated_at = strftime('%Y-%m-%dT%H:%M:%f', 'now')"]
    params: list = [to_state]

    for col, val in kwargs.items():
        if col not in _TRANSITION_COLUMNS:
            raise ValueError(f"Invalid column in transition: {col}")
        sets.append(f"{col} = ?")
        params.append(val)

    params.append(screenshot_id)
    with get_db() as conn:
        conn.execute(
            f"UPDATE screenshots SET {', '.join(sets)} WHERE id = ?",
            params,
        )


def insert_screenshot(screenshot_id: str, prnt_url: str, img_src: str | None = None,
                       state: str = "discovered") -> bool:
    """Insert a new screenshot. Returns False if ID already exists."""
    with get_db() as conn:
        try:
            conn.execute(
                "INSERT INTO screenshots (id, prnt_url, img_src, state) VALUES (?, ?, ?, ?)",
                (screenshot_id, prnt_url, img_src, state),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def screenshot_exists(screenshot_id: str) -> bool:
    """Check if a screenshot ID is already in the database."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM screenshots WHERE id = ?", (screenshot_id,)
        ).fetchone()
        return row is not None
