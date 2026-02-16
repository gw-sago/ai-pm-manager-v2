#!/usr/bin/env python3
"""
AI PM Framework - ロック管理スクリプト テスト

Lock モジュールの機能テスト:
- acquire: ロック取得
- release: ロック解放
- check: 競合チェック
- list: ロック一覧取得
"""

import sys
import os
from pathlib import Path

# テスト対象のモジュールをインポートできるようパス設定
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest
import tempfile
import shutil
from datetime import datetime

from utils.db import get_connection, transaction, init_database, DatabaseError
from utils.validation import ValidationError
from config import DBConfig, set_db_config


class TestLockModule(unittest.TestCase):
    """ロックモジュールのテスト"""

    @classmethod
    def setUpClass(cls):
        """テスト用DB設定"""
        cls.temp_dir = tempfile.mkdtemp()
        cls.db_path = Path(cls.temp_dir) / "test.db"

        # スキーマファイルパスを取得（config.pyから取得）
        from config import get_schema_path
        schema_path = get_schema_path()

        cls.config = DBConfig(
            db_path=cls.db_path,
            schema_path=schema_path,
            data_dir=Path(cls.temp_dir) / "data",
            backup_dir=Path(cls.temp_dir) / "backup",
        )
        set_db_config(cls.config)

    @classmethod
    def tearDownClass(cls):
        """テスト後のクリーンアップ"""
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        """各テスト前にDBを初期化"""
        # DBファイルを削除して再作成
        if self.db_path.exists():
            self.db_path.unlink()

        init_database(self.db_path, self.config.schema_path)

        # module_locksテーブルとtarget_modulesカラムを追加（マイグレーション相当）
        conn = get_connection()
        try:
            # module_locksテーブルを作成
            conn.execute("""
                CREATE TABLE IF NOT EXISTS module_locks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    order_id TEXT NOT NULL,
                    module_name TEXT NOT NULL,
                    locked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
                    UNIQUE (project_id, module_name)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_module_locks_project ON module_locks(project_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_module_locks_order ON module_locks(order_id)
            """)
            # target_modulesカラムを追加（存在しない場合のみ）
            try:
                conn.execute("ALTER TABLE orders ADD COLUMN target_modules TEXT")
            except Exception:
                pass  # カラムが既に存在する場合は無視
            conn.commit()
        finally:
            conn.close()

        # テスト用データを挿入
        with transaction() as conn:
            # プロジェクト
            conn.execute("""
                INSERT INTO projects (id, name, path, status)
                VALUES ('AI_PM_PJ', 'AI PM Project', '/path/to/project', 'IN_PROGRESS')
            """)

            # ORDER
            conn.execute("""
                INSERT INTO orders (id, project_id, title, status)
                VALUES ('ORDER_094', 'AI_PM_PJ', 'Test Order 094', 'IN_PROGRESS')
            """)
            conn.execute("""
                INSERT INTO orders (id, project_id, title, status)
                VALUES ('ORDER_095', 'AI_PM_PJ', 'Test Order 095', 'IN_PROGRESS')
            """)

    def test_acquire_lock_basic(self):
        """ロック取得（基本）"""
        from lock.acquire import acquire_lock

        result = acquire_lock(
            "AI_PM_PJ",
            "ORDER_094",
            ["scripts/aipm-db", ".claude/commands"],
        )

        self.assertIsNotNone(result)
        self.assertEqual(result['project_id'], 'AI_PM_PJ')
        self.assertEqual(result['order_id'], 'ORDER_094')
        self.assertEqual(len(result['acquired']), 2)
        self.assertFalse(result['forced'])
        self.assertEqual(len(result['current_locks']), 2)

        # target_modulesが更新されていることを確認
        self.assertIn('scripts/aipm-db', result['target_modules'])
        self.assertIn('.claude/commands', result['target_modules'])

    def test_acquire_lock_already_locked(self):
        """ロック取得（既にロック済み）"""
        from lock.acquire import acquire_lock

        # 初回ロック
        acquire_lock("AI_PM_PJ", "ORDER_094", ["scripts/aipm-db"])

        # 同じORDERで再度ロック（追加）
        result = acquire_lock(
            "AI_PM_PJ",
            "ORDER_094",
            ["scripts/aipm-db", ".claude/commands"],
        )

        # scripts/aipm-dbは既にロック済み
        already_locked = [a for a in result['acquired'] if a['status'] == 'already_locked']
        newly_acquired = [a for a in result['acquired'] if a['status'] == 'acquired']

        self.assertEqual(len(already_locked), 1)
        self.assertEqual(already_locked[0]['module_name'], 'scripts/aipm-db')
        self.assertEqual(len(newly_acquired), 1)
        self.assertEqual(newly_acquired[0]['module_name'], '.claude/commands')

    def test_acquire_lock_conflict(self):
        """ロック取得（競合エラー）"""
        from lock.acquire import acquire_lock, LockConflictError

        # ORDER_094でロック
        acquire_lock("AI_PM_PJ", "ORDER_094", ["scripts/aipm-db"])

        # ORDER_095で同じモジュールをロックしようとする
        with self.assertRaises(LockConflictError) as context:
            acquire_lock("AI_PM_PJ", "ORDER_095", ["scripts/aipm-db"])

        self.assertEqual(len(context.exception.conflicts), 1)
        self.assertEqual(context.exception.conflicts[0]['order_id'], 'ORDER_094')

    def test_acquire_lock_force(self):
        """ロック取得（強制モード）"""
        from lock.acquire import acquire_lock

        # ORDER_094でロック
        acquire_lock("AI_PM_PJ", "ORDER_094", ["scripts/aipm-db"])

        # ORDER_095で強制ロック
        result = acquire_lock(
            "AI_PM_PJ",
            "ORDER_095",
            ["scripts/aipm-db"],
            force=True,
        )

        self.assertTrue(result['forced'])
        self.assertEqual(len(result['conflicts_overwritten']), 1)
        self.assertEqual(result['conflicts_overwritten'][0]['order_id'], 'ORDER_094')

        # ロックがORDER_095に移っていることを確認
        from lock.list import list_locks
        locks = list_locks("AI_PM_PJ")
        self.assertEqual(locks['total_locks'], 1)
        self.assertEqual(locks['locks'][0]['order_id'], 'ORDER_095')

    def test_release_lock_single_order(self):
        """ロック解放（単一ORDER）"""
        from lock.acquire import acquire_lock
        from lock.release import release_lock

        # ロック取得
        acquire_lock("AI_PM_PJ", "ORDER_094", ["scripts/aipm-db", ".claude/commands"])

        # ロック解放
        result = release_lock("AI_PM_PJ", "ORDER_094")

        self.assertEqual(result['released_count'], 2)
        self.assertEqual(result['remaining_count'], 0)
        self.assertFalse(result['release_all'])

    def test_release_lock_all(self):
        """ロック解放（全ORDER）"""
        from lock.acquire import acquire_lock
        from lock.release import release_lock

        # 複数ORDERでロック
        acquire_lock("AI_PM_PJ", "ORDER_094", ["scripts/aipm-db"])
        acquire_lock("AI_PM_PJ", "ORDER_095", [".claude/commands"])

        # 全ロック解放
        result = release_lock("AI_PM_PJ", release_all=True)

        self.assertEqual(result['released_count'], 2)
        self.assertEqual(result['remaining_count'], 0)
        self.assertTrue(result['release_all'])

    def test_check_conflict_no_conflict(self):
        """競合チェック（競合なし）"""
        from lock.check import check_conflict

        result = check_conflict("AI_PM_PJ", ["scripts/aipm-db", ".claude/commands"])

        self.assertFalse(result['has_conflict'])
        self.assertEqual(len(result['conflicts']), 0)
        self.assertEqual(len(result['available']), 2)

    def test_check_conflict_with_conflict(self):
        """競合チェック（競合あり）"""
        from lock.acquire import acquire_lock
        from lock.check import check_conflict

        # ORDER_094でロック
        acquire_lock("AI_PM_PJ", "ORDER_094", ["scripts/aipm-db"])

        # 競合チェック
        result = check_conflict("AI_PM_PJ", ["scripts/aipm-db", ".claude/commands"])

        self.assertTrue(result['has_conflict'])
        self.assertEqual(len(result['conflicts']), 1)
        self.assertEqual(result['conflicts'][0]['order_id'], 'ORDER_094')
        self.assertEqual(len(result['available']), 1)
        self.assertIn('.claude/commands', result['available'])

    def test_list_locks_empty(self):
        """ロック一覧（空）"""
        from lock.list import list_locks

        result = list_locks("AI_PM_PJ")

        self.assertEqual(result['total_locks'], 0)
        self.assertEqual(result['unique_orders'], 0)
        self.assertEqual(result['unique_modules'], 0)
        self.assertEqual(len(result['locks']), 0)

    def test_list_locks_multiple(self):
        """ロック一覧（複数）"""
        from lock.acquire import acquire_lock
        from lock.list import list_locks

        # 複数ORDERでロック
        acquire_lock("AI_PM_PJ", "ORDER_094", ["scripts/aipm-db", "src/module1"])
        acquire_lock("AI_PM_PJ", "ORDER_095", [".claude/commands"])

        # 全ロック一覧
        result = list_locks("AI_PM_PJ")

        self.assertEqual(result['total_locks'], 3)
        self.assertEqual(result['unique_orders'], 2)
        self.assertEqual(result['unique_modules'], 3)

    def test_list_locks_filter_order(self):
        """ロック一覧（ORDER絞り込み）"""
        from lock.acquire import acquire_lock
        from lock.list import list_locks

        # 複数ORDERでロック
        acquire_lock("AI_PM_PJ", "ORDER_094", ["scripts/aipm-db", "src/module1"])
        acquire_lock("AI_PM_PJ", "ORDER_095", [".claude/commands"])

        # ORDER_094のみ
        result = list_locks("AI_PM_PJ", order_id="ORDER_094")

        self.assertEqual(result['total_locks'], 2)
        self.assertEqual(result['unique_orders'], 1)

        for lock in result['locks']:
            self.assertEqual(lock['order_id'], 'ORDER_094')

    def test_orders_target_modules_update(self):
        """ORDERのtarget_modulesが更新されることを確認"""
        from lock.acquire import acquire_lock
        from lock.release import release_lock

        # ロック取得
        acquire_lock("AI_PM_PJ", "ORDER_094", ["scripts/aipm-db"])

        # ordersテーブルを確認
        conn = get_connection()
        try:
            cursor = conn.execute(
                "SELECT target_modules FROM orders WHERE id = ? AND project_id = ?",
                ("ORDER_094", "AI_PM_PJ")
            )
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row['target_modules'], 'scripts/aipm-db')
        finally:
            conn.close()

        # ロック解放
        release_lock("AI_PM_PJ", "ORDER_094")

        # target_modulesがクリアされていることを確認
        conn = get_connection()
        try:
            cursor = conn.execute(
                "SELECT target_modules FROM orders WHERE id = ? AND project_id = ?",
                ("ORDER_094", "AI_PM_PJ")
            )
            row = cursor.fetchone()
            self.assertIsNone(row['target_modules'])
        finally:
            conn.close()


def run_tests():
    """テスト実行"""
    # テストスイート作成
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestLockModule)

    # テスト実行
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 結果サマリ
    print("\n" + "=" * 70)
    print(f"テスト結果: {'PASS' if result.wasSuccessful() else 'FAIL'}")
    print(f"実行: {result.testsRun}")
    print(f"成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"失敗: {len(result.failures)}")
    print(f"エラー: {len(result.errors)}")
    print("=" * 70)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
