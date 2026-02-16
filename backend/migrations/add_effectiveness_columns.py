#!/usr/bin/env python3
"""
AI PM Framework - Migration: Add effectiveness tracking columns to bugs table
Version: 1.0.0
Created: 2026-02-10

Adds effectiveness tracking columns to bugs table:
- effectiveness_score: Bug pattern effectiveness (0.0-1.0, default 0.5)
- total_injections: Number of times pattern was injected (default 0)
- related_failures: Number of related failures (default 0)

Changes:
    - Add effectiveness_score REAL column (0.0-1.0 range)
    - Add total_injections INTEGER column
    - Add related_failures INTEGER column

Usage:
    python -m migrations.add_effectiveness_columns [OPTIONS]

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


def migrate_add_effectiveness_columns(conn):
    """
    bugsテーブルにeffectiveness tracking カラムを追加

    Args:
        conn: sqlite3.Connection

    Returns:
        bool: 成功時True
    """
    cursor = conn.cursor()

    # Step 1: bugsテーブルの存在確認
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='bugs'
    """)

    if not cursor.fetchone():
        raise MigrationError("bugs テーブルが存在しません。先に add_bugs_table マイグレーションを実行してください。")

    print("[INFO] bugs テーブルを確認しました")

    # Step 2: 既存カラムの確認
    cursor.execute("PRAGMA table_info(bugs)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    print(f"[INFO] 既存カラム数: {len(existing_columns)}")

    columns_to_add = {
        'effectiveness_score': 'REAL DEFAULT 0.5',
        'total_injections': 'INTEGER DEFAULT 0',
        'related_failures': 'INTEGER DEFAULT 0',
    }

    added_count = 0

    # Step 3: カラムを追加（冪等性: 既存カラムはスキップ）
    for column_name, column_def in columns_to_add.items():
        if column_name in existing_columns:
            print(f"[INFO] {column_name} カラムは既に存在します - スキップ")
        else:
            print(f"[INFO] {column_name} カラムを追加中...")
            cursor.execute(f"""
                ALTER TABLE bugs
                ADD COLUMN {column_name} {column_def}
            """)
            print(f"[INFO]   - {column_name} 追加完了")
            added_count += 1

    # Step 4: 検証
    cursor.execute("PRAGMA table_info(bugs)")
    final_columns = {row[1] for row in cursor.fetchall()}

    # 必要なカラムが全て存在することを確認
    missing_columns = set(columns_to_add.keys()) - final_columns
    if missing_columns:
        raise MigrationError(f"カラム追加に失敗しました: {missing_columns}")

    print(f"[INFO] 検証成功: {len(final_columns)}カラム確認")

    # Step 5: データ検証
    cursor.execute("SELECT COUNT(*) FROM bugs")
    bug_count = cursor.fetchone()[0]
    print(f"[INFO] 既存バグパターン数: {bug_count}")

    if bug_count > 0:
        # effectiveness_scoreのデフォルト値を確認
        cursor.execute("""
            SELECT COUNT(*) FROM bugs
            WHERE effectiveness_score = 0.5
        """)
        default_score_count = cursor.fetchone()[0]
        print(f"[INFO] effectiveness_score=0.5で初期化されたレコード数: {default_score_count}")

    if added_count > 0:
        print(f"\n[SUCCESS] {added_count} カラムを追加しました")
    else:
        print("\n[INFO] 全カラムが既に存在しています（変更なし）")

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
            "add_effectiveness_columns",
            db_path=args.db if hasattr(args, 'db') and args.db else None,
            backup=not args.no_backup,
            check_workers=not args.no_worker_check,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )

        # マイグレーション実行
        print("=" * 80)
        print("Migration: Add effectiveness tracking columns to bugs table")
        print("=" * 80)

        success = runner.run(
            migrate_add_effectiveness_columns,
            force=args.force,
        )

        if success:
            print("\n[SUCCESS] マイグレーション成功")
            if args.dry_run:
                print("   (ドライラン - 実際には変更されていません)")
            else:
                print("\n追加されたカラム:")
                print("  - effectiveness_score: バグパターンの有効性スコア (0.0-1.0)")
                print("  - total_injections: 注入回数")
                print("  - related_failures: 関連失敗数")
            return 0
        else:
            print("\n[ERROR] マイグレーション失敗")
            return 1

    except MigrationError as e:
        print(f"\n[ERROR] マイグレーションエラー: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n[ERROR] 予期しないエラー: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
