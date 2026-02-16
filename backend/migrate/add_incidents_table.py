#!/usr/bin/env python3
"""
AI PM Framework - Add INCIDENTS Table Migration Script
Version: 1.0.0

Adds INCIDENTS table for tracking and analyzing failure patterns.

Target Table:
- incidents: New table for incident tracking with columns:
  * incident_id (PK)
  * timestamp
  * project_id, order_id, task_id (nullable FKs)
  * category, severity
  * description, root_cause, resolution
  * affected_records

Uses MigrationRunner for safety:
- Automatic backup creation
- PRAGMA foreign_keys control
- Worker execution detection
- Transaction management

Usage:
    python backend/migrate/add_incidents_table.py [--dry-run] [--force]
"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db import execute_query, fetch_one
from utils.migration_base import MigrationRunner, create_migration_parser


def table_exists(conn, table_name: str) -> bool:
    """
    Check if a table exists in the database.

    Args:
        conn: Database connection
        table_name: Name of the table to check

    Returns:
        True if table exists, False otherwise
    """
    result = fetch_one(
        conn,
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return result is not None


def migrate(conn):
    """
    Run migration to add INCIDENTS table

    Args:
        conn: Database connection (managed by MigrationRunner)

    Returns:
        True if successful
    """
    cursor = conn.cursor()

    # Check if already migrated
    if table_exists(conn, 'incidents'):
        print("Migration already applied: INCIDENTS table exists")
        return True

    print("Creating INCIDENTS table...")

    # Create INCIDENTS table
    # Note: No foreign key constraints due to composite PK issues in tasks/orders tables
    # The fields are for tracking only and do not enforce referential integrity
    execute_query(
        conn,
        """
        CREATE TABLE IF NOT EXISTS incidents (
            incident_id TEXT PRIMARY KEY,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            project_id TEXT,
            order_id TEXT,
            task_id TEXT,
            category TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'MEDIUM',
            description TEXT NOT NULL,
            root_cause TEXT,
            resolution TEXT,
            affected_records TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            -- Constraints
            CHECK (severity IN ('HIGH', 'MEDIUM', 'LOW')),
            CHECK (category IN ('MIGRATION_ERROR', 'CASCADE_DELETE', 'CONSTRAINT_VIOLATION',
                                'DATA_INTEGRITY', 'CONCURRENCY_ERROR', 'FILE_LOCK_ERROR',
                                'WORKER_FAILURE', 'REVIEW_ERROR', 'SYSTEM_ERROR', 'OTHER'))
        )
        """
    )

    print("Creating indexes for INCIDENTS table...")

    # Create indexes
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_incidents_project_id ON incidents(project_id)",
        "CREATE INDEX IF NOT EXISTS idx_incidents_order_id ON incidents(order_id)",
        "CREATE INDEX IF NOT EXISTS idx_incidents_task_id ON incidents(task_id)",
        "CREATE INDEX IF NOT EXISTS idx_incidents_category ON incidents(category)",
        "CREATE INDEX IF NOT EXISTS idx_incidents_severity ON incidents(severity)",
        "CREATE INDEX IF NOT EXISTS idx_incidents_timestamp ON incidents(timestamp)",
    ]

    for idx_sql in indexes:
        execute_query(conn, idx_sql)

    print("✓ Migration completed successfully")
    print("  Created table: incidents")
    print("  Created 6 indexes for performance optimization")
    return True


def main():
    """CLI entry point"""
    parser = create_migration_parser()
    parser.description = "Add INCIDENTS table for incident tracking and analysis"
    args = parser.parse_args()

    runner = MigrationRunner(
        "add_incidents_table",
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
