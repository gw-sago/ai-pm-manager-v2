#!/usr/bin/env python3
"""
Database migration: Add target_files column to tasks table

This migration adds a target_files column to store JSON array of file paths
that each task is responsible for modifying.

Uses MigrationRunner for safety:
- Automatic backup creation
- PRAGMA foreign_keys control
- Worker execution detection
- Transaction management
"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path for imports
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
sys.path.insert(0, str(_package_root))

from utils.db import execute_query
from utils.migration_base import MigrationRunner, create_migration_parser


def migrate(conn):
    """
    Run migration to add target_files column

    Args:
        conn: Database connection (managed by MigrationRunner)

    Returns:
        True if successful
    """
    # Check if column already exists
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(tasks)")
    columns = [row[1] for row in cursor.fetchall()]

    if "target_files" in columns:
        print("Migration already applied: target_files column exists")
        return True

    # Add target_files column (JSON array stored as TEXT)
    print("Adding target_files column to tasks table...")
    execute_query(
        conn,
        "ALTER TABLE tasks ADD COLUMN target_files TEXT DEFAULT NULL"
    )

    print("✓ Migration completed successfully")
    return True


def rollback(conn):
    """
    Rollback migration by dropping target_files column

    Args:
        conn: Database connection (managed by MigrationRunner)

    Returns:
        True if successful
    """
    print("Warning: SQLite doesn't support DROP COLUMN natively.")
    print("To rollback, you need to recreate the table without target_files column.")
    print("This script does not perform automatic rollback.")
    return False


def main():
    """CLI entry point"""
    parser = create_migration_parser()
    parser.description = "Add target_files column to tasks table"
    parser.add_argument("--rollback", action="store_true", help="Rollback migration")
    args = parser.parse_args()

    migration_func = rollback if args.rollback else migrate
    migration_name = "rollback_target_files" if args.rollback else "add_target_files_to_tasks"

    runner = MigrationRunner(
        migration_name,
        db_path=args.db,
        backup=not args.no_backup,
        check_workers=not args.no_worker_check,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    try:
        success = runner.run(migration_func, force=args.force)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Migration failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
