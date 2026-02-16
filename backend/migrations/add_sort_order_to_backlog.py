#!/usr/bin/env python3
"""
AI PM Framework - Migration: Add sort_order to backlog_items
Version: 1.0.0
Created: 2026-02-06

Adds sort_order column to backlog_items table to support custom ordering.

Changes:
    - Add sort_order INTEGER DEFAULT 999 to backlog_items table
    - Create index on sort_order for efficient sorting
    - Initialize existing records with default value 999

Usage:
    python -m migrations.add_sort_order_to_backlog [OPTIONS]

Options:
    --dry-run: Preview changes without applying them
    --force: Skip worker check and force execution
    --verbose: Show detailed output
"""

import sys
from pathlib import Path

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent

if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.migration_base import MigrationRunner, MigrationError, create_migration_parser


def migrate_add_sort_order(conn):
    """
    backlog_itemsテーブルにsort_orderカラムを追加

    Args:
        conn: sqlite3.Connection

    Returns:
        bool: 成功時True
    """
    cursor = conn.cursor()

    # Step 1: カラムが既に存在するかチェック
    cursor.execute("PRAGMA table_info(backlog_items)")
    columns = [row[1] for row in cursor.fetchall()]

    if "sort_order" in columns:
        print("[INFO] sort_order カラムは既に存在します - スキップ")
        return True

    print("[INFO] backlog_items テーブルに sort_order カラムを追加...")

    # Step 2: sort_order カラムを追加
    # SQLiteのALTER TABLEは制約が少ないため、直接追加可能
    cursor.execute("""
        ALTER TABLE backlog_items
        ADD COLUMN sort_order INTEGER DEFAULT 999
    """)

    print("[INFO] sort_order カラムを追加しました")

    # Step 3: インデックスを作成
    print("[INFO] sort_order のインデックスを作成...")
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_backlog_items_sort_order
        ON backlog_items(sort_order)
    """)

    print("[INFO] インデックスを作成しました")

    # Step 4: 既存レコードの確認
    cursor.execute("SELECT COUNT(*) FROM backlog_items")
    count = cursor.fetchone()[0]
    print(f"[INFO] 既存のbacklog_itemsレコード数: {count}")

    if count > 0:
        print(f"[INFO] 既存レコードのsort_orderはデフォルト値(999)に設定されます")

    # Step 5: 検証
    cursor.execute("PRAGMA table_info(backlog_items)")
    columns_after = {row[1]: row for row in cursor.fetchall()}

    if "sort_order" not in columns_after:
        raise MigrationError("sort_order カラムの追加に失敗しました")

    sort_order_col = columns_after["sort_order"]
    print(f"[INFO] 検証成功: sort_order カラム追加完了")
    print(f"  - Type: {sort_order_col[2]}")
    print(f"  - Default: {sort_order_col[4]}")

    return True


def main():
    """メイン処理"""
    # パーサー作成
    parser = create_migration_parser()
    parser.description = __doc__
    args = parser.parse_args()

    try:
        # MigrationRunner作成
        runner = MigrationRunner(
            "add_sort_order_to_backlog",
            db_path=args.db if hasattr(args, 'db') and args.db else None,
            backup=not args.no_backup,
            check_workers=not args.no_worker_check,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )

        # マイグレーション実行
        print("=" * 80)
        print("Migration: Add sort_order to backlog_items")
        print("=" * 80)

        success = runner.run(
            migrate_add_sort_order,
            force=args.force,
        )

        if success:
            print("\n✅ マイグレーション成功")
            if args.dry_run:
                print("   (ドライラン - 実際には変更されていません)")
            else:
                print("\n次のステップ:")
                print("  1. data/schema_v2.sql を更新してください")
                print("  2. backlog/list.py に --sort-by sort_order を追加してください")
                print("  3. backlog/update.py に --sort-order N を追加してください")
            return 0
        else:
            print("\n❌ マイグレーション失敗")
            return 1

    except MigrationError as e:
        print(f"\n❌ マイグレーションエラー: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n❌ 予期しないエラー: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
