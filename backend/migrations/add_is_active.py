#!/usr/bin/env python3
"""
AI PM Framework - Add is_active Column Migration Script
Version: 1.0.0

Adds the `is_active` column to the `projects` table for active/inactive project switching.

Target Table:
- projects: Add `is_active` column (INTEGER 0/1, DEFAULT 1, NOT NULL)

Usage:
    python backend/migrations/add_is_active.py [--check] [--migrate] [--dry-run]

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


def has_is_active_column(cursor) -> bool:
    """
    Check if the projects table has the is_active column.

    Returns:
        True if is_active column exists, False otherwise.
    """
    columns = get_column_info(cursor, 'projects')
    column_names = [col[1] for col in columns]
    return 'is_active' in column_names


def create_backup(db_path: str) -> str:
    """Create a backup of the database."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{db_path}.backup_{timestamp}"
    shutil.copy2(db_path, backup_path)
    return backup_path


def migrate_add_is_active(cursor, dry_run: bool = False) -> bool:
    """
    Add is_active column to projects table.

    Args:
        cursor: SQLite cursor
        dry_run: If True, only show what would be done

    Returns:
        True if migration was performed, False if skipped.
    """
    # Check if already migrated
    if has_is_active_column(cursor):
        print("  projects: is_active column already exists (skipped)")
        return False

    if dry_run:
        print("  projects: Would add is_active column (INTEGER DEFAULT 1 NOT NULL)")
        return True

    # SQLite supports ALTER TABLE ADD COLUMN
    # The column will be added with DEFAULT value for existing rows
    cursor.execute("""
        ALTER TABLE projects
        ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1
    """)

    # Verify all existing projects have is_active = 1
    cursor.execute("SELECT COUNT(*) FROM projects WHERE is_active != 1")
    count = cursor.fetchone()[0]
    if count > 0:
        print(f"  [WARNING] {count} projects have is_active != 1, updating...")
        cursor.execute("UPDATE projects SET is_active = 1 WHERE is_active != 1")

    print("  projects: Added is_active column successfully")
    return True


def run_migration(db_path: str, dry_run: bool = False, force: bool = False) -> bool:
    """
    Run the is_active column migration.

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
        already_migrated = has_is_active_column(cursor)

        print("\n=== Add is_active Column Migration ===")
        print(f"Database: {db_path}")
        print(f"\nColumn Status:")
        print(f"  is_active: {'Exists' if already_migrated else 'Missing'}")

        if already_migrated:
            print("\n[INFO] projects table already has is_active column.")
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
        migrate_add_is_active(cursor, dry_run)

        # Commit transaction
        if not dry_run:
            cursor.execute("COMMIT")
            print("\n[OK] Migration completed successfully!")
        else:
            print("\n[DRY-RUN] No changes were made.")

        # Verify migration
        if not dry_run:
            if has_is_active_column(cursor):
                # Show current state
                cursor.execute("SELECT id, name, is_active FROM projects")
                projects = cursor.fetchall()
                print(f"\n[VERIFIED] {len(projects)} projects with is_active column:")
                for proj in projects:
                    print(f"  - {proj[0]}: {proj[1]} (is_active={proj[2]})")
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
        has_column = has_is_active_column(cursor)

        # Get project count if column exists
        project_info = []
        if has_column:
            cursor.execute("SELECT id, name, is_active FROM projects")
            project_info = cursor.fetchall()

        return {
            'has_is_active': has_column,
            'projects': project_info
        }
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description='Add is_active column to projects table'
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

        print("\n=== is_active Column Migration Status ===")
        print(f"Database: {db_path}")
        print(f"\nColumn Status:")
        print(f"  is_active: {'Exists' if status['has_is_active'] else 'Missing'}")

        if status['has_is_active']:
            print(f"\nProjects ({len(status['projects'])}):")
            for proj in status['projects']:
                status_str = "Active" if proj[2] == 1 else "Inactive"
                print(f"  - {proj[0]}: {proj[1]} ({status_str})")
        else:
            print("\nTo migrate, run:")
            print("  python backend/migrations/add_is_active.py --migrate")

        sys.exit(0)


if __name__ == '__main__':
    main()
