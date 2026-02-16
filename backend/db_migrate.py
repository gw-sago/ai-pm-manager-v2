#!/usr/bin/env python3
"""
AI PM Manager - Database Migration Script

Migrates existing aipm.db from AI_PM project to ai-pm-manager-v2.

Migration Process:
1. Validates source database schema compatibility
2. Creates new database from schema_v2.sql
3. Copies data from source to target database
4. Validates data integrity after migration
5. Creates backup of source database

Usage:
    python db_migrate.py --source SOURCE_DB [--target TARGET_DB] [--backup-dir DIR]

Options:
    --source PATH        Source database path (required)
    --target PATH        Target database path (default: ../data/aipm.db)
    --backup-dir PATH    Backup directory (default: ../data/backups)
    --skip-backup        Skip backup creation (not recommended)
    --dry-run            Validate only, don't perform migration
"""

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class MigrationError(Exception):
    """Migration operation error"""
    pass


def get_default_paths():
    """Get default target database path"""
    script_dir = Path(__file__).resolve().parent
    target_db_path = script_dir.parent / "data" / "aipm.db"
    backup_dir = script_dir.parent / "data" / "backups"
    schema_path = script_dir.parent / "data" / "schema_v2.sql"
    return target_db_path, backup_dir, schema_path


def get_table_list(conn: sqlite3.Connection) -> List[str]:
    """Get list of tables in database"""
    cursor = conn.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
    """)
    return [row[0] for row in cursor.fetchall()]


def get_table_row_count(conn: sqlite3.Connection, table_name: str) -> int:
    """Get row count for a table"""
    cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
    return cursor.fetchone()[0]


def validate_source_database(
    source_path: Path,
    verbose: bool = True
) -> Tuple[bool, Dict[str, int]]:
    """
    Validate source database compatibility

    Args:
        source_path: Source database path
        verbose: Print validation messages

    Returns:
        (is_valid, table_counts): Validation result and table row counts
    """
    if not source_path.exists():
        if verbose:
            print(f"エラー: ソースDBが見つかりません: {source_path}")
        return False, {}

    if verbose:
        print(f"ソースDB検証中: {source_path}")

    try:
        conn = sqlite3.connect(str(source_path))
        conn.row_factory = sqlite3.Row

        # Get tables
        tables = get_table_list(conn)

        # Required core tables
        required_tables = {
            'projects', 'orders', 'tasks', 'backlog_items',
            'status_transitions', 'bugs', 'error_patterns'
        }

        missing_tables = required_tables - set(tables)

        if missing_tables:
            if verbose:
                print(f"エラー: 必須テーブルが不足しています: {missing_tables}")
            conn.close()
            return False, {}

        # Get row counts
        table_counts = {}
        for table in tables:
            table_counts[table] = get_table_row_count(conn, table)

        if verbose:
            print(f"✓ ソースDB検証完了")
            print(f"  テーブル数: {len(tables)}")
            print(f"  データ行数:")
            for table, count in sorted(table_counts.items()):
                if count > 0:
                    print(f"    {table}: {count} rows")

        conn.close()
        return True, table_counts

    except Exception as e:
        if verbose:
            print(f"エラー: ソースDB検証失敗")
            print(f"  {type(e).__name__}: {e}")
        return False, {}


def create_backup(
    source_path: Path,
    backup_dir: Path,
    verbose: bool = True
) -> Optional[Path]:
    """
    Create backup of source database

    Args:
        source_path: Source database path
        backup_dir: Backup directory
        verbose: Print progress messages

    Returns:
        Path to backup file, or None if failed
    """
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"aipm_backup_{timestamp}.db"
    backup_path = backup_dir / backup_filename

    if verbose:
        print(f"バックアップ作成中: {backup_path}")

    try:
        shutil.copy2(source_path, backup_path)

        if verbose:
            size_mb = backup_path.stat().st_size / (1024 * 1024)
            print(f"✓ バックアップ完了 ({size_mb:.2f} MB)")

        return backup_path

    except Exception as e:
        if verbose:
            print(f"エラー: バックアップ作成失敗")
            print(f"  {type(e).__name__}: {e}")
        return None


def migrate_data(
    source_path: Path,
    target_path: Path,
    schema_path: Path,
    verbose: bool = True
) -> bool:
    """
    Migrate data from source to target database

    Args:
        source_path: Source database path
        target_path: Target database path (will be created)
        schema_path: Schema SQL file path
        verbose: Print progress messages

    Returns:
        bool: True if successful
    """
    if verbose:
        print(f"\nデータ移行開始")
        print(f"  ソース: {source_path}")
        print(f"  ターゲット: {target_path}")

    try:
        # Initialize target database with schema
        if target_path.exists():
            if verbose:
                print(f"  既存のターゲットDBを削除: {target_path}")
            target_path.unlink()

        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Read schema
        schema_sql = schema_path.read_text(encoding="utf-8")

        # Create target database
        target_conn = sqlite3.connect(str(target_path))
        target_conn.row_factory = sqlite3.Row
        target_conn.execute("PRAGMA foreign_keys = OFF")  # Disable during migration
        target_conn.executescript(schema_sql)
        target_conn.commit()

        # Open source database
        source_conn = sqlite3.connect(str(source_path))
        source_conn.row_factory = sqlite3.Row

        # Get tables from source
        tables = get_table_list(source_conn)

        # Tables to migrate (excluding internal tables)
        migrate_tables = [
            t for t in tables
            if not t.startswith('sqlite_') and t != 'schema_version'
        ]

        if verbose:
            print(f"\n  移行対象テーブル: {len(migrate_tables)}")

        # Migrate data table by table
        migrated_counts = {}

        for table in migrate_tables:
            try:
                # Get all rows from source
                cursor = source_conn.execute(f"SELECT * FROM {table}")
                rows = cursor.fetchall()

                if not rows:
                    if verbose:
                        print(f"    {table}: スキップ (データなし)")
                    continue

                # Get column names
                column_names = [description[0] for description in cursor.description]
                placeholders = ', '.join(['?' for _ in column_names])
                columns_str = ', '.join(column_names)

                # Insert into target
                insert_sql = f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders})"

                for row in rows:
                    target_conn.execute(insert_sql, tuple(row))

                migrated_counts[table] = len(rows)

                if verbose:
                    print(f"    {table}: {len(rows)} rows")

            except Exception as e:
                if verbose:
                    print(f"    {table}: エラー - {e}")
                # Continue with other tables

        target_conn.commit()

        # Re-enable foreign keys
        target_conn.execute("PRAGMA foreign_keys = ON")
        target_conn.commit()

        source_conn.close()
        target_conn.close()

        if verbose:
            total_rows = sum(migrated_counts.values())
            print(f"\n✓ データ移行完了")
            print(f"  移行テーブル数: {len(migrated_counts)}")
            print(f"  総移行行数: {total_rows}")

        return True

    except Exception as e:
        if verbose:
            print(f"\n✗ エラー: データ移行失敗")
            print(f"  {type(e).__name__}: {e}")

        # Clean up partial target database
        if target_path.exists():
            target_path.unlink()

        return False


def validate_migration(
    source_path: Path,
    target_path: Path,
    verbose: bool = True
) -> bool:
    """
    Validate migrated data integrity

    Args:
        source_path: Source database path
        target_path: Target database path
        verbose: Print validation messages

    Returns:
        bool: True if validation passed
    """
    if verbose:
        print(f"\n移行データ検証中...")

    try:
        source_conn = sqlite3.connect(str(source_path))
        target_conn = sqlite3.connect(str(target_path))

        source_tables = get_table_list(source_conn)
        target_tables = get_table_list(target_conn)

        # Validate row counts match
        mismatches = []

        for table in source_tables:
            if table == 'schema_version':
                continue

            if table not in target_tables:
                if verbose:
                    print(f"  警告: ターゲットにテーブルが存在しません: {table}")
                continue

            source_count = get_table_row_count(source_conn, table)
            target_count = get_table_row_count(target_conn, table)

            if source_count != target_count:
                mismatches.append(
                    f"{table}: source={source_count}, target={target_count}"
                )

        source_conn.close()
        target_conn.close()

        if mismatches:
            if verbose:
                print(f"✗ 検証失敗: 行数が一致しません")
                for mismatch in mismatches:
                    print(f"    {mismatch}")
            return False

        if verbose:
            print(f"✓ 検証完了: データ整合性OK")

        return True

    except Exception as e:
        if verbose:
            print(f"✗ 検証エラー: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="AI PM Manager - Database Migration Script",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    default_target, default_backup_dir, default_schema = get_default_paths()

    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Source database path (required)"
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=default_target,
        help=f"Target database path (default: {default_target})"
    )
    parser.add_argument(
        "--schema-path",
        type=Path,
        default=default_schema,
        help=f"Schema file path (default: {default_schema})"
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=default_backup_dir,
        help=f"Backup directory (default: {default_backup_dir})"
    )
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="Skip backup creation (not recommended)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate only, don't perform migration"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress output messages"
    )

    args = parser.parse_args()

    verbose = not args.quiet

    # Step 1: Validate source database
    is_valid, table_counts = validate_source_database(args.source, verbose)

    if not is_valid:
        sys.exit(1)

    if args.dry_run:
        if verbose:
            print("\n✓ Dry-run完了: ソースDBは移行可能です")
        sys.exit(0)

    # Step 2: Create backup
    if not args.skip_backup:
        backup_path = create_backup(args.source, args.backup_dir, verbose)
        if not backup_path:
            if verbose:
                print("\nエラー: バックアップ作成失敗のため移行を中止します")
            sys.exit(1)
    else:
        if verbose:
            print("\n警告: バックアップをスキップします")

    # Step 3: Migrate data
    success = migrate_data(
        source_path=args.source,
        target_path=args.target,
        schema_path=args.schema_path,
        verbose=verbose
    )

    if not success:
        sys.exit(1)

    # Step 4: Validate migration
    validation_ok = validate_migration(args.source, args.target, verbose)

    if not validation_ok:
        if verbose:
            print("\n警告: 移行後の検証で不整合が検出されました")
            print("バックアップからの復元を検討してください")
        sys.exit(1)

    if verbose:
        print("\n✓ 移行完了")
        print(f"  ターゲットDB: {args.target}")
        if not args.skip_backup:
            print(f"  バックアップ: {backup_path}")

    sys.exit(0)


if __name__ == "__main__":
    main()
