#!/usr/bin/env python3
"""
AI PM Framework - Migration: Add cost/complexity tracking columns to tasks table
Version: 1.0.0
Created: 2026-02-10

Adds cost and complexity tracking columns to tasks table:
- complexity_score: Task complexity score (0-100)
- estimated_tokens: Estimated token count
- actual_tokens: Actual token usage
- cost_usd: Cost in USD

Changes:
    - Add complexity_score INTEGER DEFAULT NULL to tasks table
    - Add estimated_tokens INTEGER DEFAULT NULL to tasks table
    - Add actual_tokens INTEGER DEFAULT NULL to tasks table
    - Add cost_usd REAL DEFAULT NULL to tasks table

Usage:
    python -m migrations.add_cost_columns [OPTIONS]

Options:
    --dry-run: Preview changes without applying them
    --force: Skip worker check and force execution
    --verbose: Show detailed output
"""

import sys
from pathlib import Path

# Path setup
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent

if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.migration_base import MigrationRunner, MigrationError, create_migration_parser


def migrate_add_cost_columns(conn):
    """
    tasksテーブルにcost/complexity tracking カラムを追加

    Args:
        conn: sqlite3.Connection

    Returns:
        bool: Success True
    """
    cursor = conn.cursor()

    # Step 1: tasks table existence check
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='tasks'
    """)

    if not cursor.fetchone():
        raise MigrationError("tasks テーブルが存在しません。")

    print("[INFO] tasks テーブルを確認しました")

    # Step 2: Check existing columns
    cursor.execute("PRAGMA table_info(tasks)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    print(f"[INFO] 既存カラム数: {len(existing_columns)}")

    # Columns to add (ordered)
    columns_to_add = [
        ('complexity_score', 'INTEGER DEFAULT NULL'),
        ('estimated_tokens', 'INTEGER DEFAULT NULL'),
        ('actual_tokens', 'INTEGER DEFAULT NULL'),
        ('cost_usd', 'REAL DEFAULT NULL'),
    ]

    added_count = 0

    # Step 3: Add columns (idempotent: skip existing columns)
    for column_name, column_def in columns_to_add:
        if column_name in existing_columns:
            print(f"[INFO] {column_name} カラムは既に存在します - スキップ")
        else:
            print(f"[INFO] {column_name} カラムを追加中...")
            cursor.execute(f"""
                ALTER TABLE tasks
                ADD COLUMN {column_name} {column_def}
            """)
            print(f"[INFO]   - {column_name} 追加完了")
            added_count += 1

    # Step 4: Verify
    cursor.execute("PRAGMA table_info(tasks)")
    final_columns = {row[1] for row in cursor.fetchall()}

    # Confirm all required columns exist
    required_columns = {col_name for col_name, _ in columns_to_add}
    missing_columns = required_columns - final_columns
    if missing_columns:
        raise MigrationError(f"カラム追加に失敗しました: {missing_columns}")

    print(f"[INFO] 検証成功: {len(final_columns)}カラム確認")

    # Step 5: Data verification
    cursor.execute("SELECT COUNT(*) FROM tasks")
    task_count = cursor.fetchone()[0]
    print(f"[INFO] 既存タスク数: {task_count}")

    if task_count > 0:
        # Verify new columns are NULL
        cursor.execute("""
            SELECT COUNT(*) FROM tasks
            WHERE complexity_score IS NULL
              AND estimated_tokens IS NULL
              AND actual_tokens IS NULL
              AND cost_usd IS NULL
        """)
        null_count = cursor.fetchone()[0]
        print(f"[INFO] 新規カラムがNULLのレコード数: {null_count}/{task_count}")

    if added_count > 0:
        print(f"\n[SUCCESS] {added_count} カラムを追加しました")
    else:
        print("\n[INFO] 全カラムが既に存在しています（変更なし）")

    return True


def main():
    """Main entry point"""
    # Create parser
    parser = create_migration_parser()
    parser.description = __doc__
    args = parser.parse_args()

    try:
        # Create MigrationRunner
        runner = MigrationRunner(
            'add_cost_columns',
            db_path=args.db if hasattr(args, 'db') and args.db else None,
            backup=not args.no_backup,
            check_workers=not args.no_worker_check,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )

        # Run migration
        print('=' * 80)
        print('Migration: Add cost/complexity tracking columns to tasks table')
        print('=' * 80)

        success = runner.run(
            migrate_add_cost_columns,
            force=args.force,
        )

        if success:
            print('\n[SUCCESS] マイグレーション成功')
            if args.dry_run:
                print('   (ドライラン - 実際には変更されていません)')
            else:
                print('\n追加されたカラム:')
                print('  - complexity_score: タスク難易度スコア (0-100)')
                print('  - estimated_tokens: 推定トークン数')
                print('  - actual_tokens: 実際のトークン使用量')
                print('  - cost_usd: コスト (USD)')
            return 0
        else:
            print('\n[ERROR] マイグレーション失敗')
            return 1

    except MigrationError as e:
        print(f'\n[ERROR] マイグレーションエラー: {e}', file=sys.stderr)
        return 1
    except Exception as e:
        print(f'\n[ERROR] 予期しないエラー: {e}', file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
