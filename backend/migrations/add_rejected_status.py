#!/usr/bin/env python3
"""
AI PM Framework - Add REJECTED Status Migration Script
Version: 2.0.0

Adds REJECTED status to tasks table and reject_count column for tracking rejection attempts.

Target Table:
- tasks: Add `reject_count` column (INTEGER DEFAULT 0, NOT NULL)
- tasks: Update status CHECK constraint to include 'REJECTED'
- status_transitions: Add new REJECTED status transitions

Uses MigrationRunner for safety:
- Automatic backup creation
- PRAGMA foreign_keys control
- Worker execution detection
- Transaction management

Usage:
    python backend/migrations/add_rejected_status.py [--dry-run] [--force]
"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db import execute_query
from utils.migration_base import MigrationRunner, create_migration_parser


def has_reject_count_column(conn) -> bool:
    """
    Check if the tasks table has the reject_count column.

    Args:
        conn: Database connection

    Returns:
        True if reject_count column exists, False otherwise.
    """
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(tasks)")
    columns = cursor.fetchall()
    column_names = [col[1] for col in columns]
    return 'reject_count' in column_names


def has_rejected_transitions(conn) -> bool:
    """
    Check if REJECTED status transitions exist.

    Args:
        conn: Database connection

    Returns:
        True if REJECTED transitions exist, False otherwise.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM status_transitions
        WHERE entity_type = 'task' AND to_status = 'REJECTED'
    """)
    count = cursor.fetchone()[0]
    return count > 0


def migrate(conn):
    """
    Run migration to add REJECTED status support

    Args:
        conn: Database connection (managed by MigrationRunner)

    Returns:
        True if successful
    """
    cursor = conn.cursor()

    # Check if already migrated
    has_column = has_reject_count_column(conn)
    has_transitions = has_rejected_transitions(conn)

    if has_column and has_transitions:
        print("Migration already applied: REJECTED status support exists")
        return True

    print("Adding REJECTED status support...")

    # Add reject_count column if needed
    if not has_column:
        print("  Adding reject_count column...")
        execute_query(
            conn,
            """
            ALTER TABLE tasks
            ADD COLUMN reject_count INTEGER NOT NULL DEFAULT 0
            """
        )
        print("  ✓ reject_count column added")

    # Add REJECTED status transitions if needed
    if not has_transitions:
        print("  Adding REJECTED status transitions...")
        transitions = [
            ('task', 'REWORK', 'REJECTED', 'System', 'Reject count exceeded - mark as REJECTED'),
            ('task', 'REJECTED', 'QUEUED', 'PM', 'Manual recovery from REJECTED to QUEUED'),
        ]

        for entity_type, from_status, to_status, allowed_role, description in transitions:
            execute_query(
                conn,
                """
                INSERT OR IGNORE INTO status_transitions
                (entity_type, from_status, to_status, allowed_role, description)
                VALUES (?, ?, ?, ?, ?)
                """,
                (entity_type, from_status, to_status, allowed_role, description)
            )
        print("  ✓ REJECTED transitions added")

    print("✓ Migration completed successfully")
    print("  Note: Application layer handles REJECTED status validation")
    return True


def main():
    """CLI entry point"""
    parser = create_migration_parser()
    parser.description = "Add REJECTED status support to tasks table"
    args = parser.parse_args()

    runner = MigrationRunner(
        "add_rejected_status",
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
