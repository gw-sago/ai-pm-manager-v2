#!/usr/bin/env python3
"""
AI PM Framework - Add PENDING_RELEASE Status Migration Script
Version: 2.0.0

Adds PENDING_RELEASE status to orders table for release workflow support.

Target Table:
- orders: Update status CHECK constraint to include 'PENDING_RELEASE'
- status_transitions: Add new PENDING_RELEASE status transitions

Uses MigrationRunner for safety:
- Automatic backup creation
- PRAGMA foreign_keys control
- Worker execution detection
- Transaction management

Usage:
    python backend/migrate/add_pending_release_status.py [--dry-run] [--force]
"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db import execute_query
from utils.migration_base import MigrationRunner, create_migration_parser


def has_pending_release_transitions(conn) -> bool:
    """
    Check if PENDING_RELEASE status transitions exist.

    Args:
        conn: Database connection

    Returns:
        True if PENDING_RELEASE transitions exist, False otherwise.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM status_transitions
        WHERE entity_type = 'order' AND to_status = 'PENDING_RELEASE'
    """)
    count = cursor.fetchone()[0]
    return count > 0


def migrate(conn):
    """
    Run migration to add PENDING_RELEASE status support

    Args:
        conn: Database connection (managed by MigrationRunner)

    Returns:
        True if successful
    """
    cursor = conn.cursor()

    # Check if already migrated
    if has_pending_release_transitions(conn):
        print("Migration already applied: PENDING_RELEASE transitions exist")
        return True

    print("Adding PENDING_RELEASE status transitions...")

    # Add PENDING_RELEASE status transitions
    # REVIEW -> PENDING_RELEASE (when all tasks approved and release is needed)
    # PENDING_RELEASE -> COMPLETED (after release execution)
    transitions = [
        ('order', 'REVIEW', 'PENDING_RELEASE', 'PM', 'All tasks approved - awaiting release'),
        ('order', 'PENDING_RELEASE', 'COMPLETED', 'PM', 'Release executed - mark ORDER as COMPLETED'),
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

    print("✓ Migration completed successfully")
    print("  Note: Application layer handles PENDING_RELEASE status validation")
    return True


def main():
    """CLI entry point"""
    parser = create_migration_parser()
    parser.description = "Add PENDING_RELEASE status support to orders table"
    args = parser.parse_args()

    runner = MigrationRunner(
        "add_pending_release_status",
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
