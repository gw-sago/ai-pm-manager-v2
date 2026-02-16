#!/usr/bin/env python3
"""
Database migration: Add file_locks table for parallel task execution

This migration adds a file_locks table to manage file locking for parallel task execution.

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

from utils.db import get_connection, execute_query, table_exists, DatabaseError
from utils.migration_base import MigrationRunner, create_migration_parser


def migrate(conn):
    """
    Run migration to add file_locks table

    Args:
        conn: Database connection (managed by MigrationRunner)

    Returns:
        True if successful
    """
    # Check if table already exists
    if table_exists(conn, "file_locks"):
        print("Migration already applied: file_locks table exists")
        return True

    # Create file_locks table
    print("Creating file_locks table...")
    execute_query(
        conn,
        """
        CREATE TABLE IF NOT EXISTS file_locks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            locked_at DATETIME NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id),
            FOREIGN KEY (task_id, project_id) REFERENCES tasks(id, project_id),
            UNIQUE(project_id, file_path)
        )
        """
    )

    # Create index for faster lookups
    execute_query(
        conn,
        "CREATE INDEX idx_file_locks_project_file ON file_locks(project_id, file_path)"
    )

    execute_query(
        conn,
        "CREATE INDEX idx_file_locks_task ON file_locks(project_id, task_id)"
    )

    print("✓ Migration completed successfully")
    return True


def rollback(conn):
    """
    Rollback migration by dropping file_locks table

    Args:
        conn: Database connection (managed by MigrationRunner)

    Returns:
        True if successful
    """
    if not table_exists(conn, "file_locks"):
        print("Nothing to rollback: file_locks table doesn't exist")
        return True

    print("Dropping file_locks table...")
    execute_query(conn, "DROP TABLE IF EXISTS file_locks")

    print("✓ Rollback completed successfully")
    return True


def main():
    """CLI entry point"""
    parser = create_migration_parser()
    parser.description = "Add file_locks table for parallel task execution"
    parser.add_argument("--rollback", action="store_true", help="Rollback migration")
    args = parser.parse_args()

    migration_func = rollback if args.rollback else migrate
    migration_name = "rollback_file_locks" if args.rollback else "add_file_locks_table"

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
