#!/usr/bin/env python3
"""
AI PM Manager - Database Initialization Script

Initializes a new empty database from schema_v2.sql template.
Called during first-time app startup or when creating a new project database.

Usage:
    python db_init.py [--db-path PATH] [--schema-path PATH]

Options:
    --db-path PATH       Database file path (default: ../data/aipm.db)
    --schema-path PATH   Schema file path (default: ../data/schema_v2.sql)
    --force              Force re-initialization (WARNING: destroys existing data)
"""

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Optional


def get_default_paths():
    """Get default database and schema paths relative to script location"""
    script_dir = Path(__file__).resolve().parent
    db_path = script_dir.parent / "data" / "aipm.db"
    schema_path = script_dir.parent / "data" / "schema_v2.sql"
    return db_path, schema_path


def init_database(
    db_path: Path,
    schema_path: Path,
    force: bool = False,
    verbose: bool = True
) -> bool:
    """
    Initialize database from schema file

    Args:
        db_path: Target database file path
        schema_path: Schema SQL file path
        force: If True, delete existing DB and recreate
        verbose: Print progress messages

    Returns:
        bool: True if successful, False otherwise
    """
    # Check if database already exists
    if db_path.exists():
        if not force:
            if verbose:
                print(f"エラー: データベースが既に存在します: {db_path}")
                print("既存DBを削除して再作成する場合は --force オプションを使用してください")
            return False
        else:
            if verbose:
                print(f"警告: 既存データベースを削除します: {db_path}")
            db_path.unlink()

    # Check schema file exists
    if not schema_path.exists():
        if verbose:
            print(f"エラー: スキーマファイルが見つかりません: {schema_path}")
        return False

    # Create parent directory if needed
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if verbose:
        print(f"データベースを初期化中: {db_path}")
        print(f"スキーマファイル: {schema_path}")

    try:
        # Read schema SQL
        schema_sql = schema_path.read_text(encoding="utf-8")

        # Create database and execute schema
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON")

        # Execute schema script
        conn.executescript(schema_sql)
        conn.commit()

        # Verify tables were created
        cursor = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table'
            ORDER BY name
        """)
        tables = [row[0] for row in cursor.fetchall()]

        if verbose:
            print(f"\n✓ データベース初期化完了")
            print(f"  作成されたテーブル数: {len(tables)}")
            print(f"  テーブル: {', '.join(tables)}")

        conn.close()
        return True

    except Exception as e:
        if verbose:
            print(f"\n✗ エラー: データベース初期化に失敗しました")
            print(f"  {type(e).__name__}: {e}")

        # Clean up partial database file
        if db_path.exists():
            db_path.unlink()

        return False


def create_empty_template(
    output_path: Path,
    schema_path: Path,
    verbose: bool = True
) -> bool:
    """
    Create an empty database template file

    Args:
        output_path: Output template file path
        schema_path: Schema SQL file path
        verbose: Print progress messages

    Returns:
        bool: True if successful
    """
    if verbose:
        print(f"空のDBテンプレートを作成中: {output_path}")

    success = init_database(
        db_path=output_path,
        schema_path=schema_path,
        force=True,
        verbose=verbose
    )

    if success and verbose:
        print(f"\n✓ テンプレート作成完了: {output_path}")
        print(f"  サイズ: {output_path.stat().st_size} bytes")

    return success


def main():
    parser = argparse.ArgumentParser(
        description="AI PM Manager - Database Initialization Script",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    default_db_path, default_schema_path = get_default_paths()

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
        "--force",
        action="store_true",
        help="Force re-initialization (WARNING: destroys existing data)"
    )
    parser.add_argument(
        "--template",
        type=Path,
        help="Create empty template file at specified path"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress output messages"
    )

    args = parser.parse_args()

    verbose = not args.quiet

    # Template mode
    if args.template:
        success = create_empty_template(
            output_path=args.template,
            schema_path=args.schema_path,
            verbose=verbose
        )
        sys.exit(0 if success else 1)

    # Normal initialization mode
    success = init_database(
        db_path=args.db_path,
        schema_path=args.schema_path,
        force=args.force,
        verbose=verbose
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
