#!/usr/bin/env python3
"""
AI PM Framework - Add module_locks Table Migration Script
Version: 1.0.0

Adds the `module_locks` table and `target_modules` column for concurrent order execution.

Changes:
1. Create `module_locks` table for tracking module locks
2. Add `target_modules` column to `orders` table (TEXT, nullable)

Usage:
    python backend/migrate/add_module_locks.py [--check] [--migrate] [--dry-run]

Options:
    --check     Check if migration is needed (default action)
    --migrate   Perform the migration
    --dry-run   Show what would be done without making changes
    --force     Skip confirmation prompts
"""

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_db_path


def get_column_info(cursor, table_name: str) -> list:
    """Get column information for a table."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    return cursor.fetchall()


def table_exists(cursor, table_name: str) -> bool:
    """Check if a table exists."""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def has_target_modules_column(cursor) -> bool:
    """
    Check if the orders table has the target_modules column.

    Returns:
        True if target_modules column exists, False otherwise.
    """
    columns = get_column_info(cursor, 'orders')
    column_names = [col[1] for col in columns]
    return 'target_modules' in column_names


def create_backup(db_path: str) -> str:
    """Create a backup of the database."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{db_path}.backup_{timestamp}"
    shutil.copy2(db_path, backup_path)
    return backup_path


def migrate_create_module_locks_table(cursor, dry_run: bool = False) -> bool:
    """
    Create the module_locks table.

    Args:
        cursor: SQLite cursor
        dry_run: If True, only show what would be done

    Returns:
        True if migration was performed, False if skipped.
    """
    if table_exists(cursor, 'module_locks'):
        print("  module_locks: Table already exists (skipped)")
        return False

    if dry_run:
        print("  module_locks: Would create table")
        return True

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS module_locks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            order_id TEXT NOT NULL,
            module_name TEXT NOT NULL,
            locked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id, project_id) REFERENCES orders(id, project_id) ON DELETE CASCADE,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            UNIQUE (project_id, module_name)
        )
    """)

    # Create indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_module_locks_project ON module_locks(project_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_module_locks_order ON module_locks(order_id)
    """)

    print("  module_locks: Created table with indexes successfully")
    return True


def migrate_add_target_modules_column(cursor, dry_run: bool = False) -> bool:
    """
    Add target_modules column to orders table.

    Args:
        cursor: SQLite cursor
        dry_run: If True, only show what would be done

    Returns:
        True if migration was performed, False if skipped.
    """
    if has_target_modules_column(cursor):
        print("  orders.target_modules: Column already exists (skipped)")
        return False

    if dry_run:
        print("  orders.target_modules: Would add column (TEXT, nullable)")
        return True

    cursor.execute("""
        ALTER TABLE orders
        ADD COLUMN target_modules TEXT
    """)

    print("  orders.target_modules: Added column successfully")
    return True


def run_migration(db_path: str, dry_run: bool = False, force: bool = False) -> bool:
    """
    Run the module_locks migration.

    Args:
        db_path: Path to the database file
        dry_run: Show what would be done without making changes
        force: Skip confirmation prompts

    Returns:
        True if migration was successful or not needed
    """
    if not os.path.exists(db_path):
        print(f"Error: Database file not found: {db_path}")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check current status
        table_exists_flag = table_exists(cursor, 'module_locks')
        column_exists_flag = has_target_modules_column(cursor)

        print("\n=== Add module_locks Table Migration ===")
        print(f"Database: {db_path}")
        print(f"\nMigration Status:")
        print(f"  module_locks table: {'Exists' if table_exists_flag else 'Missing'}")
        print(f"  orders.target_modules: {'Exists' if column_exists_flag else 'Missing'}")

        if table_exists_flag and column_exists_flag:
            print("\n[INFO] All migrations already applied.")
            return True

        if dry_run:
            print("\n=== Dry Run - Changes that would be made ===")
        else:
            print("\n=== Running Migration ===")

        if not dry_run and not force:
            response = input("\nProceed with migration? [y/N]: ")
            if response.lower() != 'y':
                print("Migration cancelled.")
                return False

        # Create backup
        if not dry_run:
            backup_path = create_backup(str(db_path))
            print(f"\n[BACKUP] Created: {backup_path}")

        # Begin transaction
        if not dry_run:
            cursor.execute("BEGIN TRANSACTION")

        # Run migrations
        print("\nMigrating:")
        migrate_create_module_locks_table(cursor, dry_run)
        migrate_add_target_modules_column(cursor, dry_run)

        # Commit transaction
        if not dry_run:
            cursor.execute("COMMIT")
            print("\n[OK] Migration completed successfully!")
        else:
            print("\n[DRY-RUN] No changes were made.")

        # Verify migration
        if not dry_run:
            verified = True

            if table_exists(cursor, 'module_locks'):
                cursor.execute("SELECT COUNT(*) FROM module_locks")
                count = cursor.fetchone()[0]
                print(f"\n[VERIFIED] module_locks table exists (rows: {count})")
            else:
                print("\n[ERROR] module_locks table verification failed.")
                verified = False

            if has_target_modules_column(cursor):
                print("[VERIFIED] orders.target_modules column exists")
            else:
                print("[ERROR] orders.target_modules column verification failed.")
                verified = False

            return verified

        return True

    except Exception as e:
        print(f"\n[ERROR] Migration failed: {e}")
        if not dry_run:
            cursor.execute("ROLLBACK")
            print("[ROLLBACK] Changes have been rolled back.")
        return False

    finally:
        conn.close()


def check_migration_status(db_path: str) -> dict:
    """
    Check the migration status of the database.

    Args:
        db_path: Path to the database file

    Returns:
        Migration status dict
    """
    if not os.path.exists(db_path):
        return {'error': f'Database file not found: {db_path}'}

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        has_table = table_exists(cursor, 'module_locks')
        has_column = has_target_modules_column(cursor)

        # Get lock count if table exists
        lock_info = {}
        if has_table:
            cursor.execute("SELECT COUNT(*) FROM module_locks")
            lock_info['total_locks'] = cursor.fetchone()[0]

        return {
            'has_module_locks_table': has_table,
            'has_target_modules_column': has_column,
            'lock_info': lock_info
        }
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description='Add module_locks table and target_modules column'
    )
    parser.add_argument(
        '--check',
        action='store_true',
        help='Check migration status (default action)'
    )
    parser.add_argument(
        '--migrate',
        action='store_true',
        help='Perform the migration'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Skip confirmation prompts'
    )
    parser.add_argument(
        '--db',
        type=str,
        help='Database path (default: data/aipm.db)'
    )

    args = parser.parse_args()

    # Get database path
    db_path = args.db if args.db else str(get_db_path())

    if args.migrate or args.dry_run:
        success = run_migration(
            db_path,
            dry_run=args.dry_run,
            force=args.force
        )
        sys.exit(0 if success else 1)
    else:
        # Default: check status
        status = check_migration_status(db_path)

        if 'error' in status:
            print(f"Error: {status['error']}")
            sys.exit(1)

        print("\n=== module_locks Migration Status ===")
        print(f"Database: {db_path}")
        print(f"\nMigration Status:")
        print(f"  module_locks table: {'Exists' if status['has_module_locks_table'] else 'Missing'}")
        print(f"  orders.target_modules: {'Exists' if status['has_target_modules_column'] else 'Missing'}")

        if status['has_module_locks_table']:
            info = status['lock_info']
            print(f"\nLock Statistics:")
            print(f"  Total locks: {info['total_locks']}")

        needs_migration = not status['has_module_locks_table'] or not status['has_target_modules_column']
        if needs_migration:
            print("\nTo migrate, run:")
            print("  python backend/migrate/add_module_locks.py --migrate")

        sys.exit(0)


if __name__ == '__main__':
    main()
