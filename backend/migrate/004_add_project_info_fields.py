#!/usr/bin/env python3
"""
Migration 004: Add project information fields (description, purpose, metadata)

Adds columns to projects table for storing comprehensive project information.

Usage:
    python migrate/004_add_project_info_fields.py [--dry-run] [--verbose]
"""

import argparse
import sqlite3
import sys
from pathlib import Path

# Add parent directory to path for imports
_current_dir = Path(__file__).resolve().parent
_backend_root = _current_dir.parent
_repo_root = _backend_root.parent

if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from utils.migration_base import MigrationRunner, MigrationError


def migration_logic(conn: sqlite3.Connection) -> bool:
    """
    Apply migration: Add description, purpose, and metadata columns to projects table

    Args:
        conn: Database connection (transaction managed by MigrationRunner)

    Returns:
        bool: True if successful
    """
    cursor = conn.cursor()

    # Check if columns already exist
    cursor.execute("PRAGMA table_info(projects)")
    columns = {row[1] for row in cursor.fetchall()}

    added_columns = []

    # Add description column if not exists
    if 'description' not in columns:
        cursor.execute("ALTER TABLE projects ADD COLUMN description TEXT")
        added_columns.append('description')
        print("  ✓ Added column: description")
    else:
        print("  ⊘ Column already exists: description")

    # Add purpose column if not exists
    if 'purpose' not in columns:
        cursor.execute("ALTER TABLE projects ADD COLUMN purpose TEXT")
        added_columns.append('purpose')
        print("  ✓ Added column: purpose")
    else:
        print("  ⊘ Column already exists: purpose")

    # Add metadata column if not exists
    if 'metadata' not in columns:
        cursor.execute("ALTER TABLE projects ADD COLUMN metadata TEXT")
        added_columns.append('metadata')
        print("  ✓ Added column: metadata")
    else:
        print("  ⊘ Column already exists: metadata")

    if added_columns:
        print(f"\n  Added {len(added_columns)} column(s): {', '.join(added_columns)}")
        return True
    else:
        print("\n  No columns added (all already exist)")
        return True


def main():
    parser = argparse.ArgumentParser(
        description="Migration 004: Add project information fields"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry-run mode (no actual changes)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        help="Database file path (default: ../data/aipm.db)"
    )

    args = parser.parse_args()

    # Determine DB path
    if args.db_path:
        db_path = args.db_path
    else:
        db_path = _repo_root / "data" / "aipm.db"

    print(f"\n{'='*60}")
    print(f"Migration 004: Add project information fields")
    print(f"{'='*60}")
    print(f"Database: {db_path}")
    print(f"Dry-run: {args.dry_run}")
    print(f"{'='*60}\n")

    try:
        runner = MigrationRunner(
            migration_name="004_add_project_info_fields",
            db_path=db_path,
            backup=not args.dry_run,
            check_workers=True,
            dry_run=args.dry_run,
            verbose=args.verbose
        )

        success = runner.run(migration_logic)

        if success:
            print(f"\n{'='*60}")
            print("✓ Migration completed successfully")
            print(f"{'='*60}\n")
            return 0
        else:
            print(f"\n{'='*60}")
            print("✗ Migration failed")
            print(f"{'='*60}\n")
            return 1

    except MigrationError as e:
        print(f"\n✗ Migration Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
