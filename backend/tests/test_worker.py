#!/usr/bin/env python3
"""
AI PM Framework - Worker割当スクリプト テスト

Worker モジュールの機能テスト:
- get_used_workers: 使用中Worker取得
- get_next_worker: 次のWorker識別子取得
- get_worker_status: Worker状況取得
"""

import sys
from pathlib import Path

# テスト対象のモジュールをインポートできるようパス設定
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest
import tempfile
import shutil

from utils.db import get_connection, transaction, init_database, DatabaseError
from utils.validation import ValidationError
from config import DBConfig, set_db_config

from worker.assign import (
    get_used_workers,
    get_used_workers_from_db,
    get_next_worker,
    get_worker_status,
    WorkerAssignmentError,
    WORKER_IDS,
)


class TestWorkerAssign(unittest.TestCase):
    """Worker割当モジュールのテスト"""

    @classmethod
    def setUpClass(cls):
        """テスト用DB設定"""
        cls.temp_dir = tempfile.mkdtemp()
        cls.db_path = Path(cls.temp_dir) / "test.db"

        # スキーマファイルパスを取得
        # tests/test_worker.py → tests → backend → ai-pm-manager-v2
        schema_path = Path(__file__).resolve().parent.parent.parent / "data" / "schema_v2.sql"

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
                VALUES ('ORDER_039', 'AI_PM_PJ', 'Test Order', 'IN_PROGRESS')
            """)

    # === Worker識別子定数テスト ===

    def test_worker_ids_count(self):
        """Worker識別子が26個（A〜Z）あることを確認"""
        self.assertEqual(len(WORKER_IDS), 26)

    def test_worker_ids_format(self):
        """Worker識別子のフォーマットを確認"""
        self.assertEqual(WORKER_IDS[0], "Worker A")
        self.assertEqual(WORKER_IDS[25], "Worker Z")

    # === get_used_workers テスト ===

    def test_get_used_workers_empty(self):
        """使用中Workerなしの場合"""
        used = get_used_workers("AI_PM_PJ")
        self.assertEqual(len(used), 0)

    def test_get_used_workers_with_in_progress(self):
        """IN_PROGRESSタスクがある場合"""
        # タスクを作成してIN_PROGRESSに
        with transaction() as conn:
            conn.execute("""
                INSERT INTO tasks (id, order_id, title, status, assignee)
                VALUES ('TASK_001', 'ORDER_039', 'Test Task 1', 'IN_PROGRESS', 'Worker A')
            """)

        used = get_used_workers("AI_PM_PJ")
        self.assertEqual(len(used), 1)
        self.assertIn("Worker A", used)

    def test_get_used_workers_multiple(self):
        """複数のIN_PROGRESSタスクがある場合"""
        with transaction() as conn:
            conn.execute("""
                INSERT INTO tasks (id, order_id, title, status, assignee)
                VALUES
                    ('TASK_001', 'ORDER_039', 'Test Task 1', 'IN_PROGRESS', 'Worker A'),
                    ('TASK_002', 'ORDER_039', 'Test Task 2', 'IN_PROGRESS', 'Worker B'),
                    ('TASK_003', 'ORDER_039', 'Test Task 3', 'IN_PROGRESS', 'Worker C')
            """)

        used = get_used_workers("AI_PM_PJ")
        self.assertEqual(len(used), 3)
        self.assertIn("Worker A", used)
        self.assertIn("Worker B", used)
        self.assertIn("Worker C", used)

    def test_get_used_workers_ignores_completed(self):
        """COMPLETEDタスクのWorkerは使用中に含まない"""
        with transaction() as conn:
            conn.execute("""
                INSERT INTO tasks (id, order_id, title, status, assignee)
                VALUES
                    ('TASK_001', 'ORDER_039', 'Test Task 1', 'IN_PROGRESS', 'Worker A'),
                    ('TASK_002', 'ORDER_039', 'Test Task 2', 'COMPLETED', 'Worker B')
            """)

        used = get_used_workers("AI_PM_PJ")
        self.assertEqual(len(used), 1)
        self.assertIn("Worker A", used)
        self.assertNotIn("Worker B", used)

    def test_get_used_workers_ignores_null_assignee(self):
        """担当者なしのタスクは無視"""
        with transaction() as conn:
            conn.execute("""
                INSERT INTO tasks (id, order_id, title, status, assignee)
                VALUES
                    ('TASK_001', 'ORDER_039', 'Test Task 1', 'IN_PROGRESS', 'Worker A'),
                    ('TASK_002', 'ORDER_039', 'Test Task 2', 'IN_PROGRESS', NULL),
                    ('TASK_003', 'ORDER_039', 'Test Task 3', 'IN_PROGRESS', '-')
            """)

        used = get_used_workers("AI_PM_PJ")
        self.assertEqual(len(used), 1)
        self.assertIn("Worker A", used)

    # === get_next_worker テスト ===

    def test_get_next_worker_first(self):
        """最初のWorkerはWorker A"""
        next_worker = get_next_worker("AI_PM_PJ")
        self.assertEqual(next_worker, "Worker A")

    def test_get_next_worker_second(self):
        """Worker Aが使用中ならWorker B"""
        with transaction() as conn:
            conn.execute("""
                INSERT INTO tasks (id, order_id, title, status, assignee)
                VALUES ('TASK_001', 'ORDER_039', 'Test Task 1', 'IN_PROGRESS', 'Worker A')
            """)

        next_worker = get_next_worker("AI_PM_PJ")
        self.assertEqual(next_worker, "Worker B")

    def test_get_next_worker_skip_used(self):
        """使用中Workerをスキップ"""
        with transaction() as conn:
            conn.execute("""
                INSERT INTO tasks (id, order_id, title, status, assignee)
                VALUES
                    ('TASK_001', 'ORDER_039', 'Test Task 1', 'IN_PROGRESS', 'Worker A'),
                    ('TASK_002', 'ORDER_039', 'Test Task 2', 'IN_PROGRESS', 'Worker B')
            """)

        next_worker = get_next_worker("AI_PM_PJ")
        self.assertEqual(next_worker, "Worker C")

    def test_get_next_worker_fill_gap(self):
        """間のWorkerが空いていれば埋める"""
        with transaction() as conn:
            conn.execute("""
                INSERT INTO tasks (id, order_id, title, status, assignee)
                VALUES
                    ('TASK_001', 'ORDER_039', 'Test Task 1', 'IN_PROGRESS', 'Worker B'),
                    ('TASK_002', 'ORDER_039', 'Test Task 2', 'IN_PROGRESS', 'Worker D')
            """)

        next_worker = get_next_worker("AI_PM_PJ")
        self.assertEqual(next_worker, "Worker A")

    def test_get_next_worker_all_used_error(self):
        """全Workerが使用中の場合エラー"""
        with transaction() as conn:
            for i, worker_id in enumerate(WORKER_IDS):
                conn.execute("""
                    INSERT INTO tasks (id, order_id, title, status, assignee)
                    VALUES (?, 'ORDER_039', ?, 'IN_PROGRESS', ?)
                """, (f"TASK_{i:03d}", f"Task {i}", worker_id))

        with self.assertRaises(WorkerAssignmentError):
            get_next_worker("AI_PM_PJ")

    # === get_worker_status テスト ===

    def test_get_worker_status_empty(self):
        """Worker状況取得（使用中なし）"""
        status = get_worker_status("AI_PM_PJ")

        self.assertEqual(status["project_id"], "AI_PM_PJ")
        self.assertEqual(status["used_count"], 0)
        self.assertEqual(status["available_count"], 26)
        self.assertEqual(status["next_worker"], "Worker A")
        self.assertEqual(status["max_workers"], 26)

    def test_get_worker_status_with_used(self):
        """Worker状況取得（使用中あり）"""
        with transaction() as conn:
            conn.execute("""
                INSERT INTO tasks (id, order_id, title, status, assignee)
                VALUES
                    ('TASK_001', 'ORDER_039', 'Test Task 1', 'IN_PROGRESS', 'Worker A'),
                    ('TASK_002', 'ORDER_039', 'Test Task 2', 'IN_PROGRESS', 'Worker C')
            """)

        status = get_worker_status("AI_PM_PJ")

        self.assertEqual(status["used_count"], 2)
        self.assertEqual(status["available_count"], 24)
        self.assertIn("Worker A", status["used_workers"])
        self.assertIn("Worker C", status["used_workers"])
        self.assertEqual(status["next_worker"], "Worker B")

    # === バリデーションテスト ===

    def test_validation_project_name(self):
        """プロジェクト名のバリデーション"""
        # 空のプロジェクト名はエラー
        with self.assertRaises(ValidationError):
            get_used_workers("")


def run_tests():
    """テスト実行"""
    # テストスイート作成
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # テストクラスを追加
    suite.addTests(loader.loadTestsFromTestCase(TestWorkerAssign))

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
