#!/usr/bin/env python3
"""
AI PM Framework - Add markdown_created Column Migration Script
Version: 1.0.0

Adds the `markdown_created` column to the `tasks` table to track Markdown file creation status.

Target Table:
- tasks: Add `markdown_created` column (INTEGER 0/1, DEFAULT 0, NOT NULL)

Usage:
    python backend/migrations/add_markdown_created.py [--check] [--migrate] [--dry-run]

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


def has_markdown_created_column(cursor) -> bool:
    """
    Check if the tasks table has the markdown_created column.

    Returns:
        True if markdown_created column exists, False otherwise.
    """
    columns = get_column_info(cursor, 'tasks')
    column_names = [col[1] for col in columns]
    return 'markdown_created' in column_names


def create_backup(db_path: str) -> str:
    """Create a backup of the database."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{db_path}.backup_{timestamp}"
    shutil.copy2(db_path, backup_path)
    return backup_path


def migrate_add_markdown_created(cursor, dry_run: bool = False) -> bool:
    """
    Add markdown_created column to tasks table.

    Args:
        cursor: SQLite cursor
        dry_run: If True, only show what would be done

    Returns:
        True if migration was performed, False if skipped.
    """
    # Check if already migrated
    if has_markdown_created_column(cursor):
        print("  tasks: markdown_created column already exists (skipped)")
        return False

    if dry_run:
        print("  tasks: Would add markdown_created column (INTEGER DEFAULT 0 NOT NULL)")
        return True

    # SQLite supports ALTER TABLE ADD COLUMN
    # The column will be added with DEFAULT value for existing rows
    cursor.execute("""
        ALTER TABLE tasks
        ADD COLUMN markdown_created INTEGER NOT NULL DEFAULT 0
    """)

    print("  tasks: Added markdown_created column successfully")
    return True


def run_migration(db_path: str, dry_run: bool = False, force: bool = False) -> bool:
    """
    Run the markdown_created column migration.

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
        already_migrated = has_markdown_created_column(cursor)

        print("\n=== Add markdown_created Column Migration ===")
        print(f"Database: {db_path}")
        print(f"\nColumn Status:")
        print(f"  markdown_created: {'Exists' if already_migrated else 'Missing'}")

        if already_migrated:
            print("\n[INFO] tasks table already has markdown_created column.")
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

        # Run migration
        print("\nMigrating:")
        migrate_add_markdown_created(cursor, dry_run)

        # Commit transaction
        if not dry_run:
            cursor.execute("COMMIT")
            print("\n[OK] Migration completed successfully!")
        else:
            print("\n[DRY-RUN] No changes were made.")

        # Verify migration
        if not dry_run:
            if has_markdown_created_column(cursor):
                # Show current state
                cursor.execute("SELECT COUNT(*) FROM tasks")
                count = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM tasks WHERE markdown_created = 0")
                count_false = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM tasks WHERE markdown_created = 1")
                count_true = cursor.fetchone()[0]
                print(f"\n[VERIFIED] tasks table now has markdown_created column:")
                print(f"  Total tasks: {count}")
                print(f"  markdown_created=0 (FALSE): {count_false}")
                print(f"  markdown_created=1 (TRUE): {count_true}")
            else:
                print("\n[ERROR] Migration verification failed.")
                return False

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
        has_column = has_markdown_created_column(cursor)

        # Get task count if column exists
        task_info = {}
        if has_column:
            cursor.execute("SELECT COUNT(*) FROM tasks")
            task_info['total'] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE markdown_created = 0")
            task_info['false_count'] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE markdown_created = 1")
            task_info['true_count'] = cursor.fetchone()[0]

        return {
            'has_markdown_created': has_column,
            'task_info': task_info
        }
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description='Add markdown_created column to tasks table'
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

        print("\n=== markdown_created Column Migration Status ===")
        print(f"Database: {db_path}")
        print(f"\nColumn Status:")
        print(f"  markdown_created: {'Exists' if status['has_markdown_created'] else 'Missing'}")

        if status['has_markdown_created']:
            info = status['task_info']
            print(f"\nTask Statistics:")
            print(f"  Total tasks: {info['total']}")
            print(f"  markdown_created=0 (FALSE): {info['false_count']}")
            print(f"  markdown_created=1 (TRUE): {info['true_count']}")
        else:
            print("\nTo migrate, run:")
            print("  python backend/migrations/add_markdown_created.py --migrate")

        sys.exit(0)


if __name__ == '__main__':
    main()
