#!/usr/bin/env python3
"""
AI PM Framework - Migration: Add bugs table
Version: 1.0.0
Created: 2026-02-09

Adds bugs table to track known bug patterns and lessons learned.

Changes:
    - Create bugs table with comprehensive fields
    - Create indexes for efficient querying
    - Support for generic (project_id=NULL) and project-specific bugs

Usage:
    python -m migrations.add_bugs_table [OPTIONS]

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


def migrate_add_bugs_table(conn):
    """
    bugsテーブルを追加

    Args:
        conn: sqlite3.Connection

    Returns:
        bool: 成功時True
    """
    cursor = conn.cursor()

    # Step 1: テーブルが既に存在するかチェック
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='bugs'
    """)

    if cursor.fetchone():
        print("[INFO] bugs テーブルは既に存在します - スキップ")
        return True

    print("[INFO] bugs テーブルを作成...")

    # Step 2: bugs テーブルを作成
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bugs (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            pattern_type TEXT,
            severity TEXT DEFAULT 'Medium',
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            solution TEXT,
            related_files TEXT,
            tags TEXT,
            occurrence_count INTEGER DEFAULT 1,
            last_occurred_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,

            CHECK (severity IN ('Critical', 'High', 'Medium', 'Low')),
            CHECK (status IN ('ACTIVE', 'FIXED', 'ARCHIVED'))
        )
    """)

    print("[INFO] bugs テーブルを作成しました")

    # Step 3: インデックスを作成
    print("[INFO] bugs テーブルのインデックスを作成...")

    indexes = [
        ("idx_bugs_project_id", "project_id"),
        ("idx_bugs_status", "status"),
        ("idx_bugs_pattern_type", "pattern_type"),
        ("idx_bugs_severity", "severity"),
    ]

    for idx_name, idx_column in indexes:
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS {idx_name}
            ON bugs({idx_column})
        """)
        print(f"[INFO]   - {idx_name} 作成完了")

    # Step 4: updated_at トリガーを作成
    print("[INFO] bugs テーブルのトリガーを作成...")
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS trigger_bugs_updated_at
        AFTER UPDATE ON bugs
        FOR EACH ROW
        BEGIN
            UPDATE bugs SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
        END
    """)

    print("[INFO] トリガーを作成しました")

    # Step 5: 検証
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='bugs'
    """)

    if not cursor.fetchone():
        raise MigrationError("bugs テーブルの作成に失敗しました")

    # インデックス検証
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='index' AND tbl_name='bugs'
    """)
    created_indexes = [row[0] for row in cursor.fetchall()]
    print(f"[INFO] 検証成功: bugs テーブル作成完了")
    print(f"  - 作成されたインデックス: {len(created_indexes)}個")

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
            "add_bugs_table",
            db_path=args.db if hasattr(args, 'db') and args.db else None,
            backup=not args.no_backup,
            check_workers=not args.no_worker_check,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )

        # マイグレーション実行
        print("=" * 80)
        print("Migration: Add bugs table")
        print("=" * 80)

        success = runner.run(
            migrate_add_bugs_table,
            force=args.force,
        )

        if success:
            print("\n✅ マイグレーション成功")
            if args.dry_run:
                print("   (ドライラン - 実際には変更されていません)")
            else:
                print("\n次のステップ:")
                print("  1. bugs/ ディレクトリ配下に add.py, list.py, update.py を作成")
                print("  2. task/execute_task.py にバグパターン注入機能を追加")
                print("  3. 既知バグパターンを登録")
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
