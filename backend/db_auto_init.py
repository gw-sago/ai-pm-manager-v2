#!/usr/bin/env python3
"""
AI PM Manager - Auto Database Initialization

Handles automatic database initialization on first app startup.
Called by Electron app to ensure database exists before operation.

Usage:
    python db_auto_init.py [--db-path PATH] [--schema-path PATH]

Returns:
    Exit code 0: Database ready (existing or newly created)
    Exit code 1: Error occurred
"""

import argparse
import sys
from pathlib import Path
from typing import Optional, Tuple

try:
    # Try relative import from db_init module
    from db_init import init_database, get_default_paths as get_init_paths
except ImportError:
    # Fallback: add parent dir to path and import
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from db_init import init_database, get_default_paths as get_init_paths


def check_database_exists(db_path: Path, verbose: bool = True) -> bool:
    """
    Check if database file exists and is valid

    Args:
        db_path: Database file path
        verbose: Print status messages

    Returns:
        bool: True if database exists and appears valid
    """
    if not db_path.exists():
        if verbose:
            print(f"データベースが見つかりません: {db_path}")
        return False

    # Basic validity check: try to open as SQLite database
    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
        result = cursor.fetchone()
        conn.close()

        if result is None:
            if verbose:
                print(f"データベースが空です: {db_path}")
            return False

        if verbose:
            print(f"既存のデータベースを検出: {db_path}")
        return True

    except Exception as e:
        if verbose:
            print(f"データベースが破損している可能性があります: {e}")
        return False


def auto_initialize_database(
    db_path: Optional[Path] = None,
    schema_path: Optional[Path] = None,
    verbose: bool = True
) -> Tuple[bool, str]:
    """
    Auto-initialize database if needed

    Args:
        db_path: Database file path (None = use default)
        schema_path: Schema file path (None = use default)
        verbose: Print progress messages

    Returns:
        (success, message): Success status and status message
    """
    # Get default paths if not provided
    if db_path is None or schema_path is None:
        default_db, default_schema = get_init_paths()
        if db_path is None:
            db_path = default_db
        if schema_path is None:
            schema_path = default_schema

    # Check if database already exists
    if check_database_exists(db_path, verbose=verbose):
        return True, f"既存のデータベースを使用: {db_path}"

    # Database doesn't exist - create new one
    if verbose:
        print(f"\n新規データベースを初期化します...")

    success = init_database(
        db_path=db_path,
        schema_path=schema_path,
        force=False,
        verbose=verbose
    )

    if success:
        return True, f"データベースを初期化しました: {db_path}"
    else:
        return False, f"データベース初期化に失敗しました"


def main():
    parser = argparse.ArgumentParser(
        description="AI PM Manager - Auto Database Initialization"
    )

    default_db_path, default_schema_path = get_init_paths()

    parser.add_argument(
        "--db-path",
        type=Path,
        default=default_db_path,
        help=f"Database file path (default: {default_db_path})"
    )
    parser.add_argument(
        "--schema-path",
        type=Path,
        default=default_schema_path,
        help=f"Schema file path (default: {default_schema_path})"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress output messages"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON (for IPC integration)"
    )

    args = parser.parse_args()

    verbose = not args.quiet

    # Auto-initialize database
    success, message = auto_initialize_database(
        db_path=args.db_path,
        schema_path=args.schema_path,
        verbose=verbose
    )

    # Output result
    if args.json:
        import json
        result = {
            "success": success,
            "message": message,
            "db_path": str(args.db_path)
        }
        print(json.dumps(result, ensure_ascii=False))
    else:
        if not verbose:
            print(message)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
