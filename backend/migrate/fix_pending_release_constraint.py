#!/usr/bin/env python3
"""
Fix PENDING_RELEASE CHECK constraint in orders table

SQLite doesn't support ALTER TABLE MODIFY CONSTRAINT, so we need to:
1. Create a new table with the updated constraint
2. Copy all data from old table
3. Drop old table
4. Rename new table

This migration uses the MigrationRunner for safety:
- Automatic backup creation
- PRAGMA foreign_keys control
- Worker execution detection
- Transaction management
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db import get_connection
from utils.migration_base import MigrationRunner, create_migration_parser


def fix_pending_release_constraint(conn):
    """
    Fix the CHECK constraint to include PENDING_RELEASE

    Args:
        conn: Database connection (managed by MigrationRunner)

    Returns:
        True if successful, False otherwise
    """
    cursor = conn.cursor()

    # Check if constraint already includes PENDING_RELEASE
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='orders'")
    result = cursor.fetchone()

    if not result:
        print("✗ orders table not found")
        return False

    schema = result[0]

    if 'PENDING_RELEASE' in schema:
        print("✓ orders table already has PENDING_RELEASE in CHECK constraint")
        return True

    print("Fixing orders table CHECK constraint to include PENDING_RELEASE...")

    # Get all dependent views
    cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='view'")
    views = cursor.fetchall()

    # Drop all views temporarily
    for view_name, _ in views:
        cursor.execute(f"DROP VIEW IF EXISTS {view_name}")
        print(f"  Dropped view: {view_name}")

    # Create new table with updated constraint
    cursor.execute("""
        CREATE TABLE orders_new (
            id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            title TEXT NOT NULL,
            priority TEXT DEFAULT 'P1',
            status TEXT NOT NULL DEFAULT 'PLANNING',
            started_at DATETIME,
            completed_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            target_modules TEXT,

            PRIMARY KEY (id, project_id),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            CHECK (priority IN ('P0', 'P1', 'P2', 'P3')),
            CHECK (status IN ('PLANNING', 'IN_PROGRESS', 'REVIEW', 'PENDING_RELEASE', 'COMPLETED', 'ON_HOLD', 'CANCELLED'))
        )
    """)

    # Copy data
    cursor.execute("""
        INSERT INTO orders_new
        SELECT * FROM orders
    """)

    # Drop old table
    cursor.execute("DROP TABLE orders")

    # Rename new table
    cursor.execute("ALTER TABLE orders_new RENAME TO orders")

    # Recreate views
    for view_name, view_sql in views:
        cursor.execute(view_sql)
        print(f"  Recreated view: {view_name}")

    print("✓ Successfully updated orders table CHECK constraint")
    return True


def main():
    """CLI entry point"""
    parser = create_migration_parser()
    parser.description = "Fix PENDING_RELEASE CHECK constraint in orders table"
    args = parser.parse_args()

    # MigrationRunner でラップして実行
    runner = MigrationRunner(
        "fix_pending_release_constraint",
        db_path=args.db,
        backup=not args.no_backup,
        check_workers=not args.no_worker_check,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    try:
        success = runner.run(fix_pending_release_constraint, force=args.force)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Migration failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
