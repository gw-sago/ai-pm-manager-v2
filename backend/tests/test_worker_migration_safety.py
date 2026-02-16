#!/usr/bin/env python3
"""
AI PM Framework - Worker実行中のマイグレーション安全機構テスト

Worker実行中にマイグレーションスクリプトが呼び出された際の
安全ガード機能をテストする。

Usage:
    python backend/tests/test_worker_migration_safety.py
"""

import sqlite3
import sys
from pathlib import Path

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
_project_root = _package_root.parent

if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import get_connection, execute_query
from utils.migration_base import check_worker_safety, MigrationRunner


def setup_test_db():
    """テスト用DBに実行中タスクを作成"""
    conn = get_connection()
    try:
        # テスト用のIN_PROGRESSタスクを作成（既存プロジェクトを使用）
        # ai_pm_managerプロジェクトとORDER_080を使用
        execute_query(
            conn,
            """
            INSERT OR REPLACE INTO tasks (
                id, project_id, order_id, title, description,
                status, assignee, priority, created_at, updated_at
            ) VALUES (
                'TASK_TEST_999', 'ai_pm_manager', 'ORDER_080',
                'Test Migration Task', 'Test migration safety check',
                'IN_PROGRESS', 'TestWorker', 'P0',
                datetime('now'), datetime('now')
            )
            """
        )
        conn.commit()
        print("✓ テスト用IN_PROGRESSタスクを作成しました")
    finally:
        conn.close()


def cleanup_test_db():
    """テスト用タスクを削除"""
    conn = get_connection()
    try:
        execute_query(
            conn,
            "DELETE FROM tasks WHERE id = 'TASK_TEST_999' AND project_id = 'ai_pm_manager'"
        )
        conn.commit()
        print("✓ テスト用タスクを削除しました")
    finally:
        conn.close()


def test_worker_safety_check():
    """Worker安全チェックのテスト"""
    print("\n=== Test 1: Worker安全チェック ===")

    # IN_PROGRESSタスクがある状態でチェック
    result = check_worker_safety(verbose=True)

    print(f"\n結果:")
    print(f"  safe: {result['safe']}")
    print(f"  running_tasks: {len(result['running_tasks'])}件")
    if result['warning']:
        print(f"  warning: {result['warning']}")

    if not result['safe']:
        print("\n✓ 正常: Worker実行中が検出されました")
        return True
    else:
        print("\n✗ エラー: Worker実行中が検出されませんでした")
        return False


def test_migration_runner_warning():
    """MigrationRunnerの警告機能テスト"""
    print("\n=== Test 2: MigrationRunnerの警告 ===")

    def dummy_migration(conn):
        """ダミーマイグレーション（何もしない）"""
        print("  (ダミーマイグレーション実行)")
        return True

    # MigrationRunnerを作成（ドライランモード）
    runner = MigrationRunner(
        "test_worker_safety",
        dry_run=True,  # ドライランモードで実行
        backup=False,  # バックアップ不要
        check_workers=True,  # Worker実行チェック有効
        verbose=True
    )

    print("\nMigrationRunnerを実行します...")
    try:
        # forceなしで実行（警告が表示されるはず）
        success = runner.run(dummy_migration, force=False)

        if success:
            print("\n✓ MigrationRunner実行完了（警告表示済み）")
            return True
        else:
            print("\n✗ MigrationRunnerがキャンセルされました")
            return False

    except Exception as e:
        print(f"\n✗ エラー: {e}")
        return False


def test_no_workers_running():
    """Worker実行なしの状態でのテスト"""
    print("\n=== Test 3: Worker実行なしの状態 ===")

    # テスト用タスクを削除
    cleanup_test_db()

    # Worker実行チェック
    result = check_worker_safety(verbose=True)

    print(f"\n結果:")
    print(f"  safe: {result['safe']}")
    print(f"  running_tasks: {len(result['running_tasks'])}件")

    if result['safe']:
        print("\n✓ 正常: Worker実行なしが確認されました")
        return True
    else:
        print("\n✗ エラー: Worker実行ありと誤検出されました")
        return False


def main():
    """メインテスト"""
    print("=" * 60)
    print("Worker実行中のマイグレーション安全機構テスト")
    print("=" * 60)

    try:
        # テスト準備
        setup_test_db()

        # テスト実行
        results = []
        results.append(("Worker安全チェック", test_worker_safety_check()))
        results.append(("MigrationRunner警告", test_migration_runner_warning()))
        results.append(("Worker実行なし", test_no_workers_running()))

        # 結果サマリー
        print("\n" + "=" * 60)
        print("テスト結果サマリー")
        print("=" * 60)

        for name, success in results:
            status = "✓ PASS" if success else "✗ FAIL"
            print(f"{status}: {name}")

        total = len(results)
        passed = sum(1 for _, success in results if success)

        print(f"\n合計: {passed}/{total} テストが成功")

        if passed == total:
            print("\n✓ すべてのテストが成功しました")
            return 0
        else:
            print("\n✗ 一部のテストが失敗しました")
            return 1

    finally:
        # クリーンアップ
        cleanup_test_db()


if __name__ == "__main__":
    sys.exit(main())
