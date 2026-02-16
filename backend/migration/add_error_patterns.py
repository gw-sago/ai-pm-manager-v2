"""
Migration: Add error_patterns table and incidents.pattern_id column.

This migration:
1. Creates the error_patterns table if it does not exist.
2. Adds pattern_id column to the incidents table (if not already present).
3. Inserts 10 initial error pattern records (INSERT OR IGNORE for idempotency).
4. Creates indexes and an updated_at trigger for error_patterns.

Safe to run multiple times (fully idempotent).
"""

import sqlite3
import os
import sys

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "aipm.db")
DB_PATH = os.path.abspath(DB_PATH)

# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------

CREATE_ERROR_PATTERNS_TABLE = """
CREATE TABLE IF NOT EXISTS error_patterns (
    id TEXT PRIMARY KEY,
    pattern_name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL CHECK (category IN ('RETRYABLE', 'SYSTEM', 'LOGIC', 'ENVIRONMENT')),
    regex_pattern TEXT NOT NULL,
    description TEXT,
    recommended_action TEXT NOT NULL CHECK (recommended_action IN ('RETRY', 'SKIP', 'ROLLBACK', 'ESCALATE')),
    max_retries INTEGER DEFAULT 3,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_error_patterns_category ON error_patterns(category);",
    "CREATE INDEX IF NOT EXISTS idx_error_patterns_recommended_action ON error_patterns(recommended_action);",
]

CREATE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS trigger_error_patterns_updated_at
AFTER UPDATE ON error_patterns
FOR EACH ROW
BEGIN
    UPDATE error_patterns SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;
"""

INITIAL_PATTERNS = [
    ("EP_001", "import_error", "RETRYABLE", r"ImportError|ModuleNotFoundError", "RETRY", 2, "モジュールインポートエラー"),
    ("EP_002", "timeout", "RETRYABLE", r"TimeoutError|timed out|timeout", "RETRY", 3, "タイムアウトエラー"),
    ("EP_003", "permission_denied", "ENVIRONMENT", r"PermissionError|Permission denied|Access denied", "ESCALATE", 0, "権限エラー"),
    ("EP_004", "file_not_found", "RETRYABLE", r"FileNotFoundError|No such file", "RETRY", 2, "ファイル不在エラー"),
    ("EP_005", "syntax_error", "LOGIC", r"SyntaxError|IndentationError", "ROLLBACK", 1, "構文エラー"),
    ("EP_006", "memory_error", "SYSTEM", r"MemoryError|out of memory|OOM", "SKIP", 0, "メモリ不足"),
    ("EP_007", "connection_error", "RETRYABLE", r"ConnectionError|ConnectionRefused|ECONNREFUSED", "RETRY", 3, "接続エラー"),
    ("EP_008", "db_locked", "RETRYABLE", r"database is locked|OperationalError.*locked", "RETRY", 3, "DB排他エラー"),
    ("EP_009", "disk_full", "SYSTEM", r"No space left|disk full|ENOSPC", "ESCALATE", 0, "ディスク容量不足"),
    ("EP_010", "api_rate_limit", "RETRYABLE", r"rate.?limit|429|too many requests", "RETRY", 3, "APIレート制限"),
]

INSERT_PATTERN = """
INSERT OR IGNORE INTO error_patterns
    (id, pattern_name, category, regex_pattern, recommended_action, max_retries, description)
VALUES (?, ?, ?, ?, ?, ?, ?);
"""


def run_migration():
    """Execute the migration."""
    print(f"[migration] Database: {DB_PATH}")

    if not os.path.exists(DB_PATH):
        print(f"[migration] ERROR: Database file not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    try:
        # ------------------------------------------------------------------
        # 1. Create error_patterns table
        # ------------------------------------------------------------------
        print("[migration] Creating error_patterns table (IF NOT EXISTS)...")
        cursor.execute(CREATE_ERROR_PATTERNS_TABLE)

        # ------------------------------------------------------------------
        # 2. Create indexes
        # ------------------------------------------------------------------
        print("[migration] Creating indexes...")
        for idx_sql in CREATE_INDEXES:
            cursor.execute(idx_sql)

        # ------------------------------------------------------------------
        # 3. Create updated_at trigger
        # ------------------------------------------------------------------
        print("[migration] Creating updated_at trigger...")
        cursor.execute(CREATE_TRIGGER)

        # ------------------------------------------------------------------
        # 4. Add pattern_id column to incidents table
        # ------------------------------------------------------------------
        print("[migration] Adding pattern_id column to incidents table...")
        try:
            cursor.execute("ALTER TABLE incidents ADD COLUMN pattern_id TEXT;")
            print("[migration]   -> pattern_id column added.")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("[migration]   -> pattern_id column already exists, skipping.")
            else:
                raise

        # ------------------------------------------------------------------
        # 5. Insert initial pattern data (10 records)
        # ------------------------------------------------------------------
        print("[migration] Inserting initial error patterns (INSERT OR IGNORE)...")
        for pattern in INITIAL_PATTERNS:
            cursor.execute(INSERT_PATTERN, pattern)
        inserted_count = cursor.rowcount  # only last INSERT, but we'll verify below

        conn.commit()

        # ------------------------------------------------------------------
        # 6. Verification
        # ------------------------------------------------------------------
        print("\n[migration] === Verification ===")

        # Count error_patterns rows
        cursor.execute("SELECT COUNT(*) FROM error_patterns;")
        total = cursor.fetchone()[0]
        print(f"[migration] error_patterns row count: {total}")

        # List all patterns
        cursor.execute("SELECT id, pattern_name, category, recommended_action, max_retries FROM error_patterns ORDER BY id;")
        rows = cursor.fetchall()
        print(f"[migration] Patterns:")
        for row in rows:
            print(f"  {row[0]}: {row[1]} ({row[2]}) -> {row[3]} (max_retries={row[4]})")

        # Verify incidents.pattern_id column exists
        cursor.execute("PRAGMA table_info(incidents);")
        columns = [col[1] for col in cursor.fetchall()]
        if "pattern_id" in columns:
            print(f"[migration] incidents.pattern_id column: EXISTS")
        else:
            print(f"[migration] incidents.pattern_id column: MISSING (ERROR)")

        print("\n[migration] Migration completed successfully.")

    except Exception as e:
        conn.rollback()
        print(f"[migration] ERROR: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
