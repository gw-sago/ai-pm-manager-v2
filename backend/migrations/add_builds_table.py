#!/usr/bin/env python3
"""
AI PM Framework - Add BUILDS Table Migration Script

Adds BUILDS table for tracking build execution status.
Projects with build artifacts (e.g., Electron apps) can record
build success/failure history in the DB.

Usage:
    python backend/migrations/add_builds_table.py [--dry-run] [--force]
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db import execute_query, fetch_one
from utils.migration_base import MigrationRunner, create_migration_parser


def table_exists(conn, table_name: str) -> bool:
    result = fetch_one(
        conn,
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return result is not None


def migrate(conn):
    """Run migration to add BUILDS table."""
    cursor = conn.cursor()

    if table_exists(conn, 'builds'):
        print("Migration already applied: builds table exists")
        return True

    print("Creating BUILDS table...")

    execute_query(
        conn,
        """
        CREATE TABLE IF NOT EXISTS builds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            order_id TEXT,
            release_id TEXT,
            build_type TEXT NOT NULL DEFAULT 'electron',
            status TEXT NOT NULL DEFAULT 'PENDING',
            build_command TEXT,
            build_output TEXT,
            artifact_path TEXT,
            started_at DATETIME,
            completed_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            CHECK (build_type IN ('electron', 'python', 'other')),
            CHECK (status IN ('PENDING', 'BUILDING', 'SUCCESS', 'FAILED', 'SKIPPED'))
        )
        """
    )

    print("Creating indexes...")

    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_builds_project_id ON builds(project_id)",
        "CREATE INDEX IF NOT EXISTS idx_builds_order_id ON builds(order_id)",
        "CREATE INDEX IF NOT EXISTS idx_builds_status ON builds(status)",
    ]

    for idx_sql in indexes:
        execute_query(conn, idx_sql)

    print("Migration completed: builds table created with 3 indexes")
    return True


def main():
    parser = create_migration_parser()
    parser.description = "Add BUILDS table for build status tracking"
    args = parser.parse_args()

    runner = MigrationRunner(
        "add_builds_table",
        db_path=args.db,
        backup=not args.no_backup,
        check_workers=not args.no_worker_check,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    try:
        success = runner.run(migrate, force=args.force)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Migration failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
