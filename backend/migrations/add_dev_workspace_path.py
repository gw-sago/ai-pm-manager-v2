#!/usr/bin/env python3
"""
マイグレーション: projectsテーブルにdev_workspace_pathカラムを追加

目的:
    プロジェクトごとの開発環境パス（ソースリポジトリパス）をDB管理し、
    Workerサブエージェントがソースコード変更を開発環境で行えるようにする。

変更内容:
    - projects テーブルに dev_workspace_path TEXT カラムを追加
    - ai_pm_manager_v2 プロジェクトに d:/your_workspace/ai-pm-manager-v2/ を設定

Usage:
    python backend/migrations/add_dev_workspace_path.py [--dry-run] [--verbose]
"""

import sys
from pathlib import Path

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent

if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.migration_base import MigrationRunner, MigrationError


def migrate():
    """マイグレーション実行"""
    dry_run = "--dry-run" in sys.argv
    verbose = "--verbose" in sys.argv

    runner = MigrationRunner(
        "add_dev_workspace_path",
        backup=True,
        check_workers=True,
        dry_run=dry_run,
        verbose=verbose,
    )

    def migration_logic(conn):
        cursor = conn.cursor()

        # カラム存在チェック
        cursor.execute("PRAGMA table_info(projects)")
        columns = [row[1] for row in cursor.fetchall()]

        if "dev_workspace_path" in columns:
            print("  dev_workspace_path カラムは既に存在します。スキップ。")
            return True

        # カラム追加
        cursor.execute(
            "ALTER TABLE projects ADD COLUMN dev_workspace_path TEXT"
        )
        print("  dev_workspace_path カラムを追加しました。")

        # ai_pm_manager_v2 にデフォルト値を設定
        cursor.execute(
            "UPDATE projects SET dev_workspace_path = ? WHERE id = ?",
            ("d:/your_workspace/ai-pm-manager-v2", "ai_pm_manager_v2"),
        )
        updated = cursor.rowcount
        if updated > 0:
            print(f"  ai_pm_manager_v2 に dev_workspace_path を設定しました。")
        else:
            print("  ai_pm_manager_v2 プロジェクトが見つかりません（後で設定可）。")

        return True

    return runner.run(migration_logic)


if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
