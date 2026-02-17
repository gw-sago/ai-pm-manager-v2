#!/usr/bin/env python3
"""
AI PM Framework - Composite Key Migration Script
Version: 2.0.0

Migrates the database from single primary keys to composite primary keys
for multi-project support.

Target Tables:
- orders: PRIMARY KEY (id) -> PRIMARY KEY (id, project_id)
- tasks: PRIMARY KEY (id) -> PRIMARY KEY (id, project_id)
- task_dependencies: Added project_id column

Usage:
    python backend/migrations/composite_key_migration.py [--check] [--backup] [--dry-run]

Options:
    --check     Check if migration is needed (default action)
    --migrate   Perform the migration
    --backup    Create backup before migration (recommended)
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


def get_table_schema(cursor, table_name: str) -> str:
    """Get the CREATE statement for a table."""
    cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    result = cursor.fetchone()
    return result[0] if result else None


def is_composite_key_migrated(cursor) -> dict:
    """
    Check if the database has been migrated to composite primary keys.

    Returns a dict with migration status for each table.
    """
    status = {
        'orders': False,
        'tasks': False,
        'task_dependencies': False,
        'overall': False
    }

    # Check orders table
    orders_schema = get_table_schema(cursor, 'orders')
    if orders_schema:
        # Check for composite primary key
        if 'PRIMARY KEY (id, project_id)' in orders_schema:
            status['orders'] = True

    # Check tasks table
    tasks_schema = get_table_schema(cursor, 'tasks')
    if tasks_schema:
        if 'PRIMARY KEY (id, project_id)' in tasks_schema:
            status['tasks'] = True

    # Check task_dependencies table
    deps_schema = get_table_schema(cursor, 'task_dependencies')
    if deps_schema:
        # Check if project_id column exists
        if 'project_id TEXT NOT NULL' in deps_schema:
            status['task_dependencies'] = True

    # Overall status
    status['overall'] = all([
        status['orders'],
        status['tasks'],
        status['task_dependencies']
    ])

    return status


def create_backup(db_path: str) -> str:
    """Create a backup of the database."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{db_path}.backup_{timestamp}"
    shutil.copy2(db_path, backup_path)
    return backup_path


def migrate_orders_table(cursor, dry_run: bool = False) -> bool:
    """
    Migrate orders table to composite primary key.

    Returns True if migration was performed, False if skipped.
    """
    schema = get_table_schema(cursor, 'orders')

    # Check if already migrated
    if 'PRIMARY KEY (id, project_id)' in schema:
        print("  orders: Already migrated (skipped)")
        return False

    if dry_run:
        print("  orders: Would migrate to composite key (id, project_id)")
        return True

    # SQLite doesn't support ALTER TABLE for primary key changes
    # We need to recreate the table

    # Step 1: Create new table with composite key
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

            PRIMARY KEY (id, project_id),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            CHECK (priority IN ('P0', 'P1', 'P2', 'P3')),
            CHECK (status IN ('PLANNING', 'IN_PROGRESS', 'REVIEW', 'COMPLETED', 'ON_HOLD', 'CANCELLED'))
        )
    """)

    # Step 2: Copy data
    cursor.execute("""
        INSERT INTO orders_new
        SELECT id, project_id, title, priority, status, started_at, completed_at, created_at, updated_at
        FROM orders
    """)

    # Step 3: Drop old table
    cursor.execute("DROP TABLE orders")

    # Step 4: Rename new table
    cursor.execute("ALTER TABLE orders_new RENAME TO orders")

    # Step 5: Recreate indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_project_id ON orders(project_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")

    print("  orders: Migrated successfully")
    return True


def migrate_tasks_table(cursor, dry_run: bool = False) -> bool:
    """
    Migrate tasks table to composite primary key.

    Returns True if migration was performed, False if skipped.
    """
    schema = get_table_schema(cursor, 'tasks')

    # Check if already migrated
    if 'PRIMARY KEY (id, project_id)' in schema:
        print("  tasks: Already migrated (skipped)")
        return False

    if dry_run:
        print("  tasks: Would migrate to composite key (id, project_id)")
        return True

    # Step 1: Create new table with composite key
    cursor.execute("""
        CREATE TABLE tasks_new (
            id TEXT NOT NULL,
            order_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            priority TEXT DEFAULT 'P1',
            status TEXT NOT NULL DEFAULT 'QUEUED',
            recommended_model TEXT DEFAULT 'Opus',
            assignee TEXT,
            started_at DATETIME,
            completed_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (id, project_id),
            FOREIGN KEY (order_id, project_id) REFERENCES orders(id, project_id) ON DELETE CASCADE,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            CHECK (priority IN ('P0', 'P1', 'P2', 'P3')),
            CHECK (status IN ('QUEUED', 'BLOCKED', 'IN_PROGRESS', 'DONE', 'IN_REVIEW', 'REWORK', 'COMPLETED', 'CANCELLED', 'SKIPPED'))
        )
    """)

    # Step 2: Check if project_id column exists in old table
    cursor.execute("PRAGMA table_info(tasks)")
    columns = [col[1] for col in cursor.fetchall()]

    if 'project_id' in columns:
        # project_id already exists, just copy all data
        cursor.execute("""
            INSERT INTO tasks_new
            SELECT id, order_id, project_id, title, description, priority, status,
                   recommended_model, assignee, started_at, completed_at, created_at, updated_at
            FROM tasks
        """)
    else:
        # Need to join with orders to get project_id
        cursor.execute("""
            INSERT INTO tasks_new
            SELECT t.id, t.order_id, o.project_id, t.title, t.description, t.priority, t.status,
                   t.recommended_model, t.assignee, t.started_at, t.completed_at, t.created_at, t.updated_at
            FROM tasks t
            JOIN orders o ON t.order_id = o.id
        """)

    # Step 3: Drop old table
    cursor.execute("DROP TABLE tasks")

    # Step 4: Rename new table
    cursor.execute("ALTER TABLE tasks_new RENAME TO tasks")

    # Step 5: Recreate indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_order_id ON tasks(order_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee)")

    print("  tasks: Migrated successfully")
    return True


def migrate_task_dependencies_table(cursor, dry_run: bool = False) -> bool:
    """
    Migrate task_dependencies table to include project_id.

    Returns True if migration was performed, False if skipped.
    """
    schema = get_table_schema(cursor, 'task_dependencies')

    # Check if already migrated
    if schema and 'project_id TEXT NOT NULL' in schema:
        print("  task_dependencies: Already migrated (skipped)")
        return False

    if dry_run:
        print("  task_dependencies: Would add project_id column and update foreign keys")
        return True

    # Step 1: Create new table with project_id
    cursor.execute("""
        CREATE TABLE task_dependencies_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            depends_on_task_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (task_id, project_id) REFERENCES tasks(id, project_id) ON DELETE CASCADE,
            FOREIGN KEY (depends_on_task_id, project_id) REFERENCES tasks(id, project_id) ON DELETE CASCADE,
            UNIQUE (task_id, depends_on_task_id, project_id)
        )
    """)

    # Step 2: Check if old table has project_id
    cursor.execute("PRAGMA table_info(task_dependencies)")
    columns = [col[1] for col in cursor.fetchall()]

    if 'project_id' in columns:
        # project_id already exists
        cursor.execute("""
            INSERT INTO task_dependencies_new (task_id, depends_on_task_id, project_id, created_at)
            SELECT task_id, depends_on_task_id, project_id, created_at
            FROM task_dependencies
        """)
    else:
        # Need to derive project_id from tasks
        cursor.execute("""
            INSERT INTO task_dependencies_new (task_id, depends_on_task_id, project_id, created_at)
            SELECT td.task_id, td.depends_on_task_id, t.project_id, td.created_at
            FROM task_dependencies td
            JOIN tasks t ON td.task_id = t.id
        """)

    # Step 3: Drop old table
    cursor.execute("DROP TABLE task_dependencies")

    # Step 4: Rename new table
    cursor.execute("ALTER TABLE task_dependencies_new RENAME TO task_dependencies")

    # Step 5: Recreate indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_dependencies_task_id ON task_dependencies(task_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_dependencies_depends_on ON task_dependencies(depends_on_task_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_dependencies_project_id ON task_dependencies(project_id)")

    print("  task_dependencies: Migrated successfully")
    return True


def update_views(cursor, dry_run: bool = False) -> bool:
    """
    Update views to use composite key joins.

    Returns True if views were updated.
    """
    if dry_run:
        print("  views: Would update to use composite key joins")
        return True

    # Drop existing views
    cursor.execute("DROP VIEW IF EXISTS v_active_tasks")
    cursor.execute("DROP VIEW IF EXISTS v_pending_reviews")
    cursor.execute("DROP VIEW IF EXISTS v_task_dependencies")
    cursor.execute("DROP VIEW IF EXISTS v_backlog_with_order")

    # Recreate views with composite key joins
    cursor.execute("""
        CREATE VIEW v_active_tasks AS
        SELECT t.*, o.title as order_title, o.status as order_status
        FROM tasks t
        JOIN orders o ON t.order_id = o.id AND t.project_id = o.project_id
        WHERE t.status IN ('QUEUED', 'BLOCKED', 'IN_PROGRESS', 'DONE', 'IN_REVIEW', 'REWORK')
    """)

    cursor.execute("""
        CREATE VIEW v_pending_reviews AS
        SELECT t.*, o.title as order_title
        FROM tasks t
        JOIN orders o ON t.order_id = o.id AND t.project_id = o.project_id
        WHERE t.status = 'DONE'
    """)

    cursor.execute("""
        CREATE VIEW v_task_dependencies AS
        SELECT
            td.task_id,
            td.depends_on_task_id,
            td.project_id,
            t1.title as task_title,
            t1.status as task_status,
            t2.title as depends_on_title,
            t2.status as depends_on_status
        FROM task_dependencies td
        JOIN tasks t1 ON td.task_id = t1.id AND td.project_id = t1.project_id
        JOIN tasks t2 ON td.depends_on_task_id = t2.id AND td.project_id = t2.project_id
    """)

    cursor.execute("""
        CREATE VIEW v_backlog_with_order AS
        SELECT b.*, o.title as order_title, o.status as order_status
        FROM backlog_items b
        LEFT JOIN orders o ON b.converted_to_order_id = o.id
    """)

    print("  views: Updated successfully")
    return True


def run_migration(db_path: str, backup: bool = True, dry_run: bool = False, force: bool = False) -> bool:
    """
    Run the composite key migration.

    Args:
        db_path: Path to the database file
        backup: Create backup before migration
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
        status = is_composite_key_migrated(cursor)

        print("\n=== Composite Key Migration Status ===")
        print(f"Database: {db_path}")
        print(f"\nTable Status:")
        print(f"  orders:            {'Migrated' if status['orders'] else 'Needs migration'}")
        print(f"  tasks:             {'Migrated' if status['tasks'] else 'Needs migration'}")
        print(f"  task_dependencies: {'Migrated' if status['task_dependencies'] else 'Needs migration'}")
        print(f"\nOverall: {'Migration complete' if status['overall'] else 'Migration needed'}")

        if status['overall']:
            print("\n[INFO] Database is already migrated to composite keys.")
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
        if backup and not dry_run:
            backup_path = create_backup(db_path)
            print(f"\n[BACKUP] Created: {backup_path}")

        # Disable foreign keys during migration
        cursor.execute("PRAGMA foreign_keys = OFF")

        # Begin transaction
        if not dry_run:
            cursor.execute("BEGIN TRANSACTION")

        # Migrate tables
        print("\nMigrating tables:")
        migrate_orders_table(cursor, dry_run)
        migrate_tasks_table(cursor, dry_run)
        migrate_task_dependencies_table(cursor, dry_run)

        # Update views
        print("\nUpdating views:")
        update_views(cursor, dry_run)

        # Commit transaction
        if not dry_run:
            cursor.execute("COMMIT")
            print("\n[OK] Migration completed successfully!")
        else:
            print("\n[DRY-RUN] No changes were made.")

        # Re-enable foreign keys
        cursor.execute("PRAGMA foreign_keys = ON")

        # Verify migration
        if not dry_run:
            status = is_composite_key_migrated(cursor)
            if status['overall']:
                print("\n[VERIFIED] All tables migrated successfully.")
            else:
                print("\n[WARNING] Migration may be incomplete. Please check the database.")

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
        status = is_composite_key_migrated(cursor)
        return status
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description='Migrate AI PM database to composite primary keys'
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
        '--backup',
        action='store_true',
        default=True,
        help='Create backup before migration (default: True)'
    )
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Skip backup creation'
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
    db_path = args.db if args.db else get_db_path()

    # Handle backup flag
    backup = args.backup and not args.no_backup

    if args.migrate or args.dry_run:
        success = run_migration(
            db_path,
            backup=backup,
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

        print("\n=== Composite Key Migration Status ===")
        print(f"Database: {db_path}")
        print(f"\nTable Status:")
        print(f"  orders:            {'Migrated' if status['orders'] else 'Needs migration'}")
        print(f"  tasks:             {'Migrated' if status['tasks'] else 'Needs migration'}")
        print(f"  task_dependencies: {'Migrated' if status['task_dependencies'] else 'Needs migration'}")
        print(f"\nOverall: {'Migration complete' if status['overall'] else 'Migration needed'}")

        if not status['overall']:
            print("\nTo migrate, run:")
            print("  python backend/migrations/composite_key_migration.py --migrate")

        sys.exit(0)


if __name__ == '__main__':
    main()
