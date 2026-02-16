#!/usr/bin/env python3
"""
AI PM Framework - Supervisor Feature Migration Script
Version: 1.0.0

Adds Supervisor-related tables and columns for cross-project management.

New Tables:
- supervisors: Supervisor master table
- cross_project_backlog: Cross-project backlog items

Modified Tables:
- projects: Add supervisor_id column

Usage:
    python backend/migrate/add_supervisor.py [--check] [--migrate] [--dry-run]

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


def get_table_exists(cursor, table_name: str) -> bool:
    """Check if a table exists."""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def get_column_info(cursor, table_name: str) -> list:
    """Get column information for a table."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    return cursor.fetchall()


def has_column(cursor, table_name: str, column_name: str) -> bool:
    """Check if a table has a specific column."""
    columns = get_column_info(cursor, table_name)
    column_names = [col[1] for col in columns]
    return column_name in column_names


def create_backup(db_path: str) -> str:
    """Create a backup of the database."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{db_path}.backup_{timestamp}"
    shutil.copy2(db_path, backup_path)
    return backup_path


def create_supervisors_table(cursor, dry_run: bool = False) -> bool:
    """Create supervisors table."""
    if get_table_exists(cursor, 'supervisors'):
        print("  supervisors: Table already exists (skipped)")
        return False

    if dry_run:
        print("  supervisors: Would create table")
        return True

    cursor.execute("""
        CREATE TABLE supervisors (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'ACTIVE',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            CHECK (status IN ('ACTIVE', 'INACTIVE'))
        )
    """)

    # Create index
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_supervisors_status ON supervisors(status)
    """)

    # Create updated_at trigger
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS trigger_supervisors_updated_at
        AFTER UPDATE ON supervisors
        FOR EACH ROW
        BEGIN
            UPDATE supervisors SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
        END
    """)

    print("  supervisors: Created table successfully")
    return True


def create_cross_project_backlog_table(cursor, dry_run: bool = False) -> bool:
    """Create cross_project_backlog table."""
    if get_table_exists(cursor, 'cross_project_backlog'):
        print("  cross_project_backlog: Table already exists (skipped)")
        return False

    if dry_run:
        print("  cross_project_backlog: Would create table")
        return True

    cursor.execute("""
        CREATE TABLE cross_project_backlog (
            id TEXT PRIMARY KEY,
            supervisor_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            priority TEXT DEFAULT 'Medium',
            status TEXT DEFAULT 'PENDING',
            assigned_project_id TEXT,
            assigned_backlog_id TEXT,
            analysis_result TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (supervisor_id) REFERENCES supervisors(id) ON DELETE CASCADE,
            FOREIGN KEY (assigned_project_id) REFERENCES projects(id) ON DELETE SET NULL,

            CHECK (priority IN ('High', 'Medium', 'Low')),
            CHECK (status IN ('PENDING', 'ANALYZING', 'ASSIGNED', 'DONE', 'CANCELED'))
        )
    """)

    # Create indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_xbacklog_supervisor_id
        ON cross_project_backlog(supervisor_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_xbacklog_status
        ON cross_project_backlog(status)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_xbacklog_assigned_project
        ON cross_project_backlog(assigned_project_id)
    """)

    # Create updated_at trigger
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS trigger_xbacklog_updated_at
        AFTER UPDATE ON cross_project_backlog
        FOR EACH ROW
        BEGIN
            UPDATE cross_project_backlog SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
        END
    """)

    print("  cross_project_backlog: Created table successfully")
    return True


def add_supervisor_id_to_projects(cursor, dry_run: bool = False) -> bool:
    """Add supervisor_id column to projects table."""
    if has_column(cursor, 'projects', 'supervisor_id'):
        print("  projects.supervisor_id: Column already exists (skipped)")
        return False

    if dry_run:
        print("  projects.supervisor_id: Would add column (TEXT, nullable, FK to supervisors)")
        return True

    cursor.execute("""
        ALTER TABLE projects
        ADD COLUMN supervisor_id TEXT REFERENCES supervisors(id)
    """)

    # Create index for the new column
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_projects_supervisor_id ON projects(supervisor_id)
    """)

    print("  projects.supervisor_id: Added column successfully")
    return True


def add_status_transitions(cursor, dry_run: bool = False) -> bool:
    """Add status transitions for cross_project_backlog."""
    # Check if transitions already exist
    cursor.execute("""
        SELECT COUNT(*) FROM status_transitions
        WHERE entity_type = 'xbacklog'
    """)
    count = cursor.fetchone()[0]

    if count > 0:
        print("  status_transitions: xbacklog entries already exist (skipped)")
        return False

    if dry_run:
        print("  status_transitions: Would add xbacklog transitions")
        return True

    transitions = [
        ('xbacklog', None, 'PENDING', 'PM', 'Create cross-project backlog item'),
        ('xbacklog', 'PENDING', 'ANALYZING', 'PM', 'Start dispatch analysis'),
        ('xbacklog', 'ANALYZING', 'ASSIGNED', 'PM', 'Assign to project'),
        ('xbacklog', 'ANALYZING', 'PENDING', 'PM', 'Cancel analysis'),
        ('xbacklog', 'ASSIGNED', 'DONE', 'PM', 'Mark as done after backlog completion'),
        ('xbacklog', 'PENDING', 'CANCELED', 'PM', 'Cancel backlog item'),
        ('xbacklog', 'ANALYZING', 'CANCELED', 'PM', 'Cancel during analysis'),
    ]

    for entity_type, from_status, to_status, allowed_role, description in transitions:
        cursor.execute("""
            INSERT OR IGNORE INTO status_transitions
            (entity_type, from_status, to_status, allowed_role, description)
            VALUES (?, ?, ?, ?, ?)
        """, (entity_type, from_status, to_status, allowed_role, description))

    print("  status_transitions: Added xbacklog transitions successfully")
    return True


def run_migration(db_path: str, dry_run: bool = False, force: bool = False) -> bool:
    """
    Run the Supervisor feature migration.

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
        has_supervisors = get_table_exists(cursor, 'supervisors')
        has_xbacklog = get_table_exists(cursor, 'cross_project_backlog')
        has_supervisor_id = has_column(cursor, 'projects', 'supervisor_id')

        print("\n=== Supervisor Feature Migration ===")
        print(f"Database: {db_path}")
        print(f"\nCurrent Status:")
        print(f"  supervisors table: {'Exists' if has_supervisors else 'Missing'}")
        print(f"  cross_project_backlog table: {'Exists' if has_xbacklog else 'Missing'}")
        print(f"  projects.supervisor_id: {'Exists' if has_supervisor_id else 'Missing'}")

        if has_supervisors and has_xbacklog and has_supervisor_id:
            print("\n[INFO] All Supervisor features already migrated.")
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
        changes = []

        if create_supervisors_table(cursor, dry_run):
            changes.append('supervisors table')

        if create_cross_project_backlog_table(cursor, dry_run):
            changes.append('cross_project_backlog table')

        if add_supervisor_id_to_projects(cursor, dry_run):
            changes.append('projects.supervisor_id column')

        if add_status_transitions(cursor, dry_run):
            changes.append('status_transitions for xbacklog')

        # Commit transaction
        if not dry_run:
            cursor.execute("COMMIT")
            print(f"\n[OK] Migration completed successfully!")
            if changes:
                print(f"     Changes: {', '.join(changes)}")
        else:
            print("\n[DRY-RUN] No changes were made.")
            if changes:
                print(f"     Would create: {', '.join(changes)}")

        # Verify migration
        if not dry_run:
            print("\n[VERIFICATION]")
            if get_table_exists(cursor, 'supervisors'):
                print("  supervisors: OK")
            else:
                print("  supervisors: FAILED")
                return False

            if get_table_exists(cursor, 'cross_project_backlog'):
                print("  cross_project_backlog: OK")
            else:
                print("  cross_project_backlog: FAILED")
                return False

            if has_column(cursor, 'projects', 'supervisor_id'):
                print("  projects.supervisor_id: OK")
            else:
                print("  projects.supervisor_id: FAILED")
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
        status = {
            'has_supervisors_table': get_table_exists(cursor, 'supervisors'),
            'has_xbacklog_table': get_table_exists(cursor, 'cross_project_backlog'),
            'has_supervisor_id_column': has_column(cursor, 'projects', 'supervisor_id'),
        }

        # Count records if tables exist
        if status['has_supervisors_table']:
            cursor.execute("SELECT COUNT(*) FROM supervisors")
            status['supervisor_count'] = cursor.fetchone()[0]

        if status['has_xbacklog_table']:
            cursor.execute("SELECT COUNT(*) FROM cross_project_backlog")
            status['xbacklog_count'] = cursor.fetchone()[0]

        if status['has_supervisor_id_column']:
            cursor.execute("SELECT COUNT(*) FROM projects WHERE supervisor_id IS NOT NULL")
            status['projects_with_supervisor'] = cursor.fetchone()[0]

        status['fully_migrated'] = all([
            status['has_supervisors_table'],
            status['has_xbacklog_table'],
            status['has_supervisor_id_column'],
        ])

        return status

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description='Add Supervisor feature tables and columns'
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

        print("\n=== Supervisor Feature Migration Status ===")
        print(f"Database: {db_path}")
        print(f"\nTable/Column Status:")
        print(f"  supervisors table: {'Exists' if status['has_supervisors_table'] else 'Missing'}")
        print(f"  cross_project_backlog table: {'Exists' if status['has_xbacklog_table'] else 'Missing'}")
        print(f"  projects.supervisor_id: {'Exists' if status['has_supervisor_id_column'] else 'Missing'}")

        if status['fully_migrated']:
            print(f"\n[OK] Fully migrated")
            if status.get('supervisor_count', 0) > 0:
                print(f"     Supervisors: {status['supervisor_count']}")
            if status.get('xbacklog_count', 0) > 0:
                print(f"     Cross-project backlogs: {status['xbacklog_count']}")
            if status.get('projects_with_supervisor', 0) > 0:
                print(f"     Projects with Supervisor: {status['projects_with_supervisor']}")
        else:
            print("\n[PENDING] Migration needed")
            print("\nTo migrate, run:")
            print("  python backend/migrate/add_supervisor.py --migrate")

        sys.exit(0)


if __name__ == '__main__':
    main()
