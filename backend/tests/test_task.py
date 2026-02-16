#!/usr/bin/env python3
"""
AI PM Framework - タスク管理スクリプト テスト

Task モジュールの機能テスト:
- create: タスク作成
- update: タスク更新（状態遷移含む）
- list: タスク一覧取得
- get: タスク詳細取得
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
from utils.transition import TransitionError
from config import DBConfig, set_db_config


class TestTaskModule(unittest.TestCase):
    """タスクモジュールのテスト"""

    @classmethod
    def setUpClass(cls):
        """テスト用DB設定"""
        cls.temp_dir = tempfile.mkdtemp()
        cls.db_path = Path(cls.temp_dir) / "test.db"

        # スキーマファイルパスを取得
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
                VALUES ('ORDER_036', 'AI_PM_PJ', 'Test Order', 'IN_PROGRESS')
            """)

    def test_create_task_basic(self):
        """タスク作成（基本）"""
        from task.create import create_task

        result = create_task(
            "AI_PM_PJ",
            "ORDER_036",
            "テストタスク",
            render=False,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["title"], "テストタスク")
        self.assertEqual(result["status"], "QUEUED")
        self.assertEqual(result["order_id"], "ORDER_036")
        self.assertTrue(result["id"].startswith("TASK_"))

    def test_create_task_with_id(self):
        """タスク作成（ID指定）"""
        from task.create import create_task

        result = create_task(
            "AI_PM_PJ",
            "ORDER_036",
            "タスクID指定テスト",
            task_id="TASK_999",
            render=False,
        )

        self.assertEqual(result["id"], "TASK_999")

    def test_create_task_with_dependencies(self):
        """タスク作成（依存あり）"""
        from task.create import create_task

        # 先に依存先タスクを作成
        dep_task = create_task(
            "AI_PM_PJ",
            "ORDER_036",
            "依存先タスク",
            task_id="TASK_100",
            render=False,
        )

        # 依存タスクを作成
        result = create_task(
            "AI_PM_PJ",
            "ORDER_036",
            "依存タスク",
            task_id="TASK_101",
            depends_on=["TASK_100"],
            render=False,
        )

        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("TASK_100", result["depends_on"])

    def test_create_task_auto_numbering(self):
        """タスク作成（自動採番）"""
        from task.create import create_task

        # 複数タスク作成で連番確認
        t1 = create_task("AI_PM_PJ", "ORDER_036", "タスク1", render=False)
        t2 = create_task("AI_PM_PJ", "ORDER_036", "タスク2", render=False)
        t3 = create_task("AI_PM_PJ", "ORDER_036", "タスク3", render=False)

        # 番号が増加していることを確認
        id1 = int(t1["id"].replace("TASK_", ""))
        id2 = int(t2["id"].replace("TASK_", ""))
        id3 = int(t3["id"].replace("TASK_", ""))

        self.assertLess(id1, id2)
        self.assertLess(id2, id3)

    def test_update_task_status(self):
        """タスク状態更新"""
        from task.create import create_task
        from task.update import update_task

        # タスク作成
        task = create_task(
            "AI_PM_PJ",
            "ORDER_036",
            "更新テスト",
            task_id="TASK_200",
            render=False,
        )
        self.assertEqual(task["status"], "QUEUED")

        # QUEUED → IN_PROGRESS
        updated = update_task(
            "AI_PM_PJ",
            "TASK_200",
            status="IN_PROGRESS",
            role="Worker",
            render=False,
        )
        self.assertEqual(updated["status"], "IN_PROGRESS")
        self.assertIsNotNone(updated.get("started_at"))

        # IN_PROGRESS → DONE
        updated = update_task(
            "AI_PM_PJ",
            "TASK_200",
            status="DONE",
            role="Worker",
            render=False,
        )
        self.assertEqual(updated["status"], "DONE")

        # DONE → COMPLETED (PM only)
        updated = update_task(
            "AI_PM_PJ",
            "TASK_200",
            status="COMPLETED",
            role="PM",
            render=False,
        )
        self.assertEqual(updated["status"], "COMPLETED")
        self.assertIsNotNone(updated.get("completed_at"))

    def test_update_task_invalid_transition(self):
        """タスク状態更新（不正な遷移）"""
        from task.create import create_task
        from task.update import update_task

        task = create_task(
            "AI_PM_PJ",
            "ORDER_036",
            "不正遷移テスト",
            task_id="TASK_300",
            render=False,
        )

        # QUEUED → COMPLETED は不正
        # TransitionErrorはDatabaseErrorでラップされる場合がある
        with self.assertRaises((TransitionError, DatabaseError)):
            update_task(
                "AI_PM_PJ",
                "TASK_300",
                status="COMPLETED",
                role="Worker",
                render=False,
            )

    def test_update_task_assignee(self):
        """タスク担当者更新"""
        from task.create import create_task
        from task.update import update_task

        task = create_task(
            "AI_PM_PJ",
            "ORDER_036",
            "担当者テスト",
            task_id="TASK_400",
            render=False,
        )

        updated = update_task(
            "AI_PM_PJ",
            "TASK_400",
            assignee="Worker A",
            role="PM",
            render=False,
        )

        self.assertEqual(updated["assignee"], "Worker A")

    def test_dependency_unblock(self):
        """依存タスク完了によるブロック解除"""
        from task.create import create_task
        from task.update import update_task
        from task.get import get_task

        # 依存先タスク
        create_task(
            "AI_PM_PJ",
            "ORDER_036",
            "依存先",
            task_id="TASK_500",
            render=False,
        )

        # 依存タスク（BLOCKED）
        blocked = create_task(
            "AI_PM_PJ",
            "ORDER_036",
            "ブロック中",
            task_id="TASK_501",
            depends_on=["TASK_500"],
            render=False,
        )
        self.assertEqual(blocked["status"], "BLOCKED")

        # 依存先を完了させる
        update_task("AI_PM_PJ", "TASK_500", status="IN_PROGRESS", role="Worker", render=False)
        update_task("AI_PM_PJ", "TASK_500", status="DONE", role="Worker", render=False)
        update_task("AI_PM_PJ", "TASK_500", status="COMPLETED", role="PM", render=False)

        # ブロック解除を確認
        unblocked = get_task("AI_PM_PJ", "TASK_501")
        self.assertEqual(unblocked["status"], "QUEUED")

    def test_list_tasks_basic(self):
        """タスク一覧取得（基本）"""
        from task.create import create_task
        from task.list import list_tasks

        create_task("AI_PM_PJ", "ORDER_036", "タスク1", task_id="TASK_600", render=False)
        create_task("AI_PM_PJ", "ORDER_036", "タスク2", task_id="TASK_601", render=False)
        create_task("AI_PM_PJ", "ORDER_036", "タスク3", task_id="TASK_602", render=False)

        tasks = list_tasks("AI_PM_PJ")

        self.assertEqual(len(tasks), 3)

    def test_list_tasks_filter_status(self):
        """タスク一覧取得（ステータスフィルタ）"""
        from task.create import create_task
        from task.update import update_task
        from task.list import list_tasks

        create_task("AI_PM_PJ", "ORDER_036", "タスク1", task_id="TASK_700", render=False)
        create_task("AI_PM_PJ", "ORDER_036", "タスク2", task_id="TASK_701", render=False)
        update_task("AI_PM_PJ", "TASK_701", status="IN_PROGRESS", role="Worker", render=False)

        queued = list_tasks("AI_PM_PJ", status=["QUEUED"])
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0]["id"], "TASK_700")

        in_progress = list_tasks("AI_PM_PJ", status=["IN_PROGRESS"])
        self.assertEqual(len(in_progress), 1)
        self.assertEqual(in_progress[0]["id"], "TASK_701")

    def test_list_tasks_filter_order(self):
        """タスク一覧取得（ORDERフィルタ）"""
        from task.create import create_task
        from task.list import list_tasks

        # 別のORDERを作成
        with transaction() as conn:
            conn.execute("""
                INSERT INTO orders (id, project_id, title, status)
                VALUES ('ORDER_037', 'AI_PM_PJ', 'Another Order', 'IN_PROGRESS')
            """)

        create_task("AI_PM_PJ", "ORDER_036", "タスク1", task_id="TASK_800", render=False)
        create_task("AI_PM_PJ", "ORDER_037", "タスク2", task_id="TASK_801", render=False)

        order36_tasks = list_tasks("AI_PM_PJ", order_id="ORDER_036")
        self.assertEqual(len(order36_tasks), 1)
        self.assertEqual(order36_tasks[0]["id"], "TASK_800")

    def test_get_task_basic(self):
        """タスク詳細取得（基本）"""
        from task.create import create_task
        from task.get import get_task

        create_task(
            "AI_PM_PJ",
            "ORDER_036",
            "詳細テスト",
            task_id="TASK_900",
            description="テスト説明",
            priority="P0",
            recommended_model="Opus",
            render=False,
        )

        task = get_task("AI_PM_PJ", "TASK_900")

        self.assertIsNotNone(task)
        self.assertEqual(task["id"], "TASK_900")
        self.assertEqual(task["title"], "詳細テスト")
        self.assertEqual(task["description"], "テスト説明")
        self.assertEqual(task["priority"], "P0")
        self.assertEqual(task["recommended_model"], "Opus")

    def test_get_task_with_dependencies(self):
        """タスク詳細取得（依存関係付き）"""
        from task.create import create_task
        from task.get import get_task

        create_task("AI_PM_PJ", "ORDER_036", "先行", task_id="TASK_910", render=False)
        create_task("AI_PM_PJ", "ORDER_036", "後続", task_id="TASK_911", depends_on=["TASK_910"], render=False)

        task = get_task("AI_PM_PJ", "TASK_911")

        self.assertEqual(len(task["depends_on"]), 1)
        self.assertEqual(task["depends_on"][0]["task_id"], "TASK_910")

        # 逆依存
        dep_task = get_task("AI_PM_PJ", "TASK_910")
        self.assertEqual(len(dep_task["dependents"]), 1)
        self.assertEqual(dep_task["dependents"][0]["task_id"], "TASK_911")

    def test_get_task_not_found(self):
        """タスク詳細取得（存在しない）"""
        from task.get import get_task

        task = get_task("AI_PM_PJ", "TASK_999")
        self.assertIsNone(task)


def run_tests():
    """テスト実行"""
    # テストスイート作成
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestTaskModule)

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
