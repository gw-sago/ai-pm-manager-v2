#!/usr/bin/env python3
"""
AI PM Framework - 統合ステータススクリプト テスト

backend/status/aipm_status.py の機能テスト:
- get_unified_status: コア関数（3モード対応）
- get_single_project_status: 単一プロジェクトモード
- get_active_projects_status: アクティブプロジェクトモード
- get_all_projects_status: 全プロジェクトモード
- format_human_readable: 人間可読フォーマット
- パフォーマンス: query_countが定数であること

TASK_339: ORDER_096 - /aipmコマンドの状態取得を統合スクリプト化（Python起動コスト削減）
"""

import sys
import json
import sqlite3
import unittest
from pathlib import Path

# テスト対象のモジュールをインポートできるようパス設定
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from status.aipm_status import (
    get_unified_status,
    get_single_project_status,
    get_active_projects_status,
    get_all_projects_status,
    format_human_readable,
)


def _create_test_db():
    """
    テスト用インメモリDBを作成しスキーマを適用する。
    各テストで独立したDB接続を返す。
    """
    schema_path = Path(__file__).resolve().parent.parent.parent / "data" / "schema_v2.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema_sql)
    return conn


# ============================================================
# ヘルパー関数
# ============================================================

def _insert_project(conn, project_id, name=None, status="IN_PROGRESS",
                    is_active=1, path="/test/path"):
    """テスト用プロジェクト挿入ヘルパー"""
    name = name or project_id
    conn.execute(
        """INSERT INTO projects (id, name, path, status, is_active)
           VALUES (?, ?, ?, ?, ?)""",
        (project_id, name, path, status, is_active),
    )
    conn.commit()


def _insert_order(conn, order_id, project_id, title=None,
                  status="IN_PROGRESS", priority="P1"):
    """テスト用ORDER挿入ヘルパー"""
    title = title or f"Order {order_id}"
    conn.execute(
        """INSERT INTO orders (id, project_id, title, status, priority)
           VALUES (?, ?, ?, ?, ?)""",
        (order_id, project_id, title, status, priority),
    )
    conn.commit()


def _insert_task(conn, task_id, order_id, project_id, title=None,
                 status="QUEUED", priority="P1", assignee=None):
    """テスト用タスク挿入ヘルパー"""
    title = title or f"Task {task_id}"
    conn.execute(
        """INSERT INTO tasks (id, order_id, project_id, title, status, priority, assignee)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (task_id, order_id, project_id, title, status, priority, assignee),
    )
    conn.commit()


def _insert_backlog_item(conn, backlog_id, project_id, title=None,
                         status="TODO", priority="Medium"):
    """テスト用バックログアイテム挿入ヘルパー"""
    title = title or f"Backlog {backlog_id}"
    conn.execute(
        """INSERT INTO backlog_items (id, project_id, title, status, priority)
           VALUES (?, ?, ?, ?, ?)""",
        (backlog_id, project_id, title, status, priority),
    )
    conn.commit()


# ============================================================
# 正常系テスト: 単一プロジェクトモード
# ============================================================


class TestSingleProjectMode(unittest.TestCase):
    """単一プロジェクトモードのテスト"""

    def setUp(self):
        self.conn = _create_test_db()

    def tearDown(self):
        self.conn.close()

    def test_single_project_returns_correct_data(self):
        """単一プロジェクト指定で正しいデータが返る"""
        _insert_project(self.conn, "PJ_A", "Project A")
        _insert_project(self.conn, "PJ_B", "Project B")
        _insert_order(self.conn, "ORDER_001", "PJ_A", "Order 1", "IN_PROGRESS")
        _insert_task(self.conn, "TASK_001", "ORDER_001", "PJ_A", "Task 1", "IN_PROGRESS")
        _insert_task(self.conn, "TASK_002", "ORDER_001", "PJ_A", "Task 2", "COMPLETED")

        result = get_single_project_status(self.conn, "PJ_A")

        self.assertEqual(result["metadata"]["mode"], "single_project")
        self.assertEqual(len(result["projects"]), 1)
        self.assertEqual(result["projects"][0]["id"], "PJ_A")
        self.assertEqual(result["projects"][0]["task_count"], 2)
        self.assertEqual(result["projects"][0]["completed_task_count"], 1)
        self.assertEqual(result["projects"][0]["in_progress_task_count"], 1)
        self.assertEqual(result["projects"][0]["task_progress_percent"], 50)

    def test_single_project_with_orders_and_tasks(self):
        """単一プロジェクトのORDER・タスク詳細が正しく返る"""
        _insert_project(self.conn, "PJ_A", "Project A")
        _insert_order(self.conn, "ORDER_001", "PJ_A", "Active Order", "IN_PROGRESS")
        _insert_order(self.conn, "ORDER_002", "PJ_A", "Completed Order", "COMPLETED")
        _insert_task(self.conn, "TASK_001", "ORDER_001", "PJ_A", "Task 1", "QUEUED")
        _insert_task(self.conn, "TASK_002", "ORDER_001", "PJ_A", "Task 2", "DONE")

        result = get_single_project_status(self.conn, "PJ_A")
        project = result["projects"][0]

        # ORDER統計
        self.assertEqual(project["order_count"], 2)
        self.assertEqual(project["active_order_count"], 1)
        self.assertEqual(project["completed_order_count"], 1)

        # アクティブORDERにタスクが含まれる
        active_orders = project["active_orders"]
        self.assertEqual(len(active_orders), 1)
        self.assertEqual(active_orders[0]["id"], "ORDER_001")
        self.assertEqual(len(active_orders[0]["tasks"]), 2)

    def test_single_project_does_not_include_other_projects(self):
        """単一プロジェクト指定時に他のプロジェクトデータが含まれない"""
        _insert_project(self.conn, "PJ_A", "Project A")
        _insert_project(self.conn, "PJ_B", "Project B")
        _insert_order(self.conn, "ORDER_001", "PJ_A", "Order A", "IN_PROGRESS")
        _insert_order(self.conn, "ORDER_001", "PJ_B", "Order B", "IN_PROGRESS")

        result = get_single_project_status(self.conn, "PJ_A")

        self.assertEqual(len(result["projects"]), 1)
        # DRAFT ordersもPJ_Aのみ含まれることを確認
        for draft in result["draft_orders"]:
            self.assertEqual(draft["project_id"], "PJ_A")


# ============================================================
# 正常系テスト: アクティブプロジェクトモード
# ============================================================


class TestActiveProjectsMode(unittest.TestCase):
    """アクティブプロジェクトモードのテスト"""

    def setUp(self):
        self.conn = _create_test_db()

    def tearDown(self):
        self.conn.close()

    def test_active_projects_only(self):
        """アクティブプロジェクトのみが返る"""
        _insert_project(self.conn, "PJ_ACTIVE", "Active Project", "IN_PROGRESS", is_active=1)
        _insert_project(self.conn, "PJ_INACTIVE", "Inactive Project", "COMPLETED", is_active=0)

        result = get_active_projects_status(self.conn)

        self.assertEqual(result["metadata"]["mode"], "active_only")
        self.assertEqual(len(result["projects"]), 1)
        self.assertEqual(result["projects"][0]["id"], "PJ_ACTIVE")

    def test_multiple_active_projects(self):
        """複数のアクティブプロジェクトが返る"""
        _insert_project(self.conn, "PJ_A", "Project A", "IN_PROGRESS", is_active=1)
        _insert_project(self.conn, "PJ_B", "Project B", "PLANNING", is_active=1)
        _insert_project(self.conn, "PJ_C", "Project C", "COMPLETED", is_active=0)

        result = get_active_projects_status(self.conn)

        self.assertEqual(len(result["projects"]), 2)
        project_ids = {p["id"] for p in result["projects"]}
        self.assertIn("PJ_A", project_ids)
        self.assertIn("PJ_B", project_ids)
        self.assertNotIn("PJ_C", project_ids)


# ============================================================
# 正常系テスト: 全プロジェクトモード
# ============================================================


class TestAllProjectsMode(unittest.TestCase):
    """全プロジェクトモードのテスト"""

    def setUp(self):
        self.conn = _create_test_db()

    def tearDown(self):
        self.conn.close()

    def test_all_projects_including_inactive(self):
        """非アクティブプロジェクトも含めて全プロジェクトが返る"""
        _insert_project(self.conn, "PJ_ACTIVE", "Active", "IN_PROGRESS", is_active=1)
        _insert_project(self.conn, "PJ_INACTIVE", "Inactive", "COMPLETED", is_active=0)
        _insert_project(self.conn, "PJ_CANCELLED", "Cancelled", "CANCELLED", is_active=0)

        result = get_all_projects_status(self.conn)

        self.assertEqual(result["metadata"]["mode"], "all")
        self.assertEqual(len(result["projects"]), 3)


# ============================================================
# JSON出力テスト
# ============================================================


class TestJsonOutput(unittest.TestCase):
    """JSON出力の互換性テスト"""

    def setUp(self):
        self.conn = _create_test_db()

    def tearDown(self):
        self.conn.close()

    def test_json_serializable(self):
        """結果がJSON直列化可能である"""
        _insert_project(self.conn, "PJ_A", "Project A")
        _insert_order(self.conn, "ORDER_001", "PJ_A", "Order 1", "IN_PROGRESS")
        _insert_task(self.conn, "TASK_001", "ORDER_001", "PJ_A", "Task 1", "QUEUED")

        result = get_unified_status(self.conn, project_id="PJ_A")

        # json.dumpsが例外を出さないことを確認
        json_str = json.dumps(result, ensure_ascii=False, indent=2, default=str)
        self.assertIsInstance(json_str, str)

        # パース可能であることも確認
        parsed = json.loads(json_str)
        self.assertIn("projects", parsed)
        self.assertIn("metadata", parsed)

    def test_json_structure(self):
        """JSONの構造が期待通りである"""
        _insert_project(self.conn, "PJ_A", "Project A")

        result = get_unified_status(self.conn, project_id="PJ_A")

        # トップレベルキーの確認
        self.assertIn("projects", result)
        self.assertIn("draft_orders", result)
        self.assertIn("backlog_summary", result)
        self.assertIn("metadata", result)

        # metadataキーの確認
        metadata = result["metadata"]
        self.assertIn("timestamp", metadata)
        self.assertIn("data_source", metadata)
        self.assertIn("mode", metadata)
        self.assertIn("query_count", metadata)
        self.assertIn("project_count", metadata)
        self.assertEqual(metadata["data_source"], "sqlite")


# ============================================================
# 人間可読フォーマットテスト
# ============================================================


class TestHumanReadableFormat(unittest.TestCase):
    """人間可読フォーマットのテスト"""

    def setUp(self):
        self.conn = _create_test_db()

    def tearDown(self):
        self.conn.close()

    def test_format_with_data(self):
        """データありの場合のフォーマットが正しい"""
        _insert_project(self.conn, "PJ_A", "Project A")
        _insert_order(self.conn, "ORDER_001", "PJ_A", "Order 1", "IN_PROGRESS", "P0")
        _insert_task(self.conn, "TASK_001", "ORDER_001", "PJ_A", "Task 1", "IN_PROGRESS", assignee="Worker A")
        _insert_task(self.conn, "TASK_002", "ORDER_001", "PJ_A", "Task 2", "COMPLETED")

        result = get_unified_status(self.conn, project_id="PJ_A")
        output = format_human_readable(result)

        # ヘッダーが含まれる
        self.assertIn("AI PM Framework - Project Status", output)
        self.assertIn("=" * 60, output)

        # プロジェクト情報が含まれる
        self.assertIn("Project A", output)
        self.assertIn("PJ_A", output)
        self.assertIn("IN_PROGRESS", output)

        # タスク進捗が含まれる
        self.assertIn("50%", output)

        # アクティブORDER情報が含まれる
        self.assertIn("ORDER_001", output)
        self.assertIn("Order 1", output)

        # タスク情報が含まれる
        self.assertIn("TASK_001", output)
        self.assertIn("Worker A", output)

    def test_format_empty_projects(self):
        """プロジェクトなしの場合のフォーマットが正しい"""
        result = get_unified_status(self.conn, project_id="NON_EXISTENT")
        output = format_human_readable(result)

        self.assertIn("AI PM Framework - Project Status", output)
        self.assertIn("プロジェクトが見つかりません", output)

    def test_format_with_draft_orders(self):
        """DRAFTオーダーがある場合のフォーマット"""
        _insert_project(self.conn, "PJ_A", "Project A")
        _insert_order(self.conn, "ORDER_D01", "PJ_A", "Draft Order 1", "DRAFT")
        _insert_order(self.conn, "ORDER_D02", "PJ_A", "Draft Order 2", "DRAFT")

        result = get_unified_status(self.conn, project_id="PJ_A")
        output = format_human_readable(result)

        self.assertIn("DRAFT ORDER", output)
        self.assertIn("ORDER_D01", output)
        self.assertIn("Draft Order 1", output)

    def test_format_with_blocked_and_rework_tasks(self):
        """BLOCKED/REWORKタスクがある場合の表示"""
        _insert_project(self.conn, "PJ_A", "Project A")
        _insert_order(self.conn, "ORDER_001", "PJ_A", "Order 1", "IN_PROGRESS")
        _insert_task(self.conn, "TASK_001", "ORDER_001", "PJ_A", "T1", "BLOCKED")
        _insert_task(self.conn, "TASK_002", "ORDER_001", "PJ_A", "T2", "REWORK")
        _insert_task(self.conn, "TASK_003", "ORDER_001", "PJ_A", "T3", "DONE")

        result = get_unified_status(self.conn, project_id="PJ_A")
        output = format_human_readable(result)

        self.assertIn("BLOCKED", output)
        self.assertIn("REWORK", output)
        self.assertIn("レビュー待ち(DONE)", output)

    def test_format_no_active_orders(self):
        """アクティブORDERがない場合の表示"""
        _insert_project(self.conn, "PJ_A", "Project A")
        _insert_order(self.conn, "ORDER_001", "PJ_A", "Completed Order", "COMPLETED")

        result = get_unified_status(self.conn, project_id="PJ_A")
        output = format_human_readable(result)

        self.assertIn("アクティブORDERなし", output)


# ============================================================
# 境界系テスト
# ============================================================


class TestBoundaryConditions(unittest.TestCase):
    """境界系テスト"""

    def setUp(self):
        self.conn = _create_test_db()

    def tearDown(self):
        self.conn.close()

    def test_nonexistent_project(self):
        """存在しないプロジェクト名指定時に空結果が返る"""
        _insert_project(self.conn, "PJ_A", "Project A")

        result = get_unified_status(self.conn, project_id="NON_EXISTENT")

        self.assertEqual(len(result["projects"]), 0)
        self.assertEqual(result["draft_orders"], [])
        self.assertEqual(result["metadata"]["mode"], "single_project")

    def test_project_with_no_orders(self):
        """ORDER/タスクが0件のプロジェクト"""
        _insert_project(self.conn, "PJ_EMPTY", "Empty Project")

        result = get_unified_status(self.conn, project_id="PJ_EMPTY")

        project = result["projects"][0]
        self.assertEqual(project["order_count"], 0)
        self.assertEqual(project["active_order_count"], 0)
        self.assertEqual(project["completed_order_count"], 0)
        self.assertEqual(project["task_count"], 0)
        self.assertEqual(project["completed_task_count"], 0)
        self.assertEqual(project["task_progress_percent"], 0)
        self.assertEqual(project["active_orders"], [])

    def test_project_with_draft_orders_only(self):
        """DRAFTオーダーのみのプロジェクト"""
        _insert_project(self.conn, "PJ_DRAFT", "Draft Only Project")
        _insert_order(self.conn, "ORDER_D01", "PJ_DRAFT", "Draft 1", "DRAFT")
        _insert_order(self.conn, "ORDER_D02", "PJ_DRAFT", "Draft 2", "DRAFT")

        result = get_unified_status(self.conn, project_id="PJ_DRAFT")

        project = result["projects"][0]
        self.assertEqual(project["order_count"], 2)
        self.assertEqual(project["active_order_count"], 0)
        self.assertEqual(project["draft_order_count"], 2)
        self.assertEqual(project["active_orders"], [])

        # draft_ordersリストに含まれること
        self.assertEqual(len(result["draft_orders"]), 2)
        draft_ids = {d["id"] for d in result["draft_orders"]}
        self.assertIn("ORDER_D01", draft_ids)
        self.assertIn("ORDER_D02", draft_ids)

    def test_order_with_no_tasks(self):
        """タスクが0件のORDER"""
        _insert_project(self.conn, "PJ_A", "Project A")
        _insert_order(self.conn, "ORDER_001", "PJ_A", "Empty Order", "IN_PROGRESS")

        result = get_unified_status(self.conn, project_id="PJ_A")

        active_orders = result["projects"][0]["active_orders"]
        self.assertEqual(len(active_orders), 1)
        self.assertEqual(active_orders[0]["task_count"], 0)
        self.assertEqual(active_orders[0]["progress_percent"], 0)
        self.assertEqual(active_orders[0]["tasks"], [])

    def test_backlog_items_table_missing(self):
        """backlog_itemsテーブルが存在しない場合"""
        _insert_project(self.conn, "PJ_A", "Project A")

        # backlog_itemsテーブルを削除
        self.conn.execute("DROP TABLE IF EXISTS backlog_items")
        self.conn.commit()

        result = get_unified_status(self.conn, project_id="PJ_A")

        # エラーにならず、backlog_summaryに適切な情報が入る
        backlog = result["backlog_summary"]
        self.assertEqual(backlog.get("total_items"), 0)
        self.assertIn("note", backlog)

    def test_no_projects_at_all(self):
        """プロジェクトが一切ない空DB"""
        result = get_unified_status(self.conn)

        self.assertEqual(result["projects"], [])
        self.assertEqual(result["draft_orders"], [])
        self.assertEqual(result["backlog_summary"], {})
        self.assertIn("metadata", result)

    def test_all_projects_inactive(self):
        """全プロジェクトが非アクティブの場合（activeモード）"""
        _insert_project(self.conn, "PJ_A", "Project A", "COMPLETED", is_active=0)
        _insert_project(self.conn, "PJ_B", "Project B", "CANCELLED", is_active=0)

        result = get_active_projects_status(self.conn)

        self.assertEqual(len(result["projects"]), 0)
        self.assertEqual(result["metadata"]["mode"], "active_only")

    def test_task_status_distribution(self):
        """全タスクステータスの分布が正しくカウントされる"""
        _insert_project(self.conn, "PJ_A", "Project A")
        _insert_order(self.conn, "ORDER_001", "PJ_A", "Order 1", "IN_PROGRESS")

        # 各ステータスのタスクを作成
        statuses = {
            "TASK_01": "QUEUED",
            "TASK_02": "IN_PROGRESS",
            "TASK_03": "BLOCKED",
            "TASK_04": "REWORK",
            "TASK_05": "DONE",
            "TASK_06": "COMPLETED",
            "TASK_07": "COMPLETED",
        }
        for tid, status in statuses.items():
            _insert_task(self.conn, tid, "ORDER_001", "PJ_A", f"Task {tid}", status)

        result = get_unified_status(self.conn, project_id="PJ_A")
        project = result["projects"][0]

        self.assertEqual(project["task_count"], 7)
        self.assertEqual(project["queued_task_count"], 1)
        self.assertEqual(project["in_progress_task_count"], 1)
        self.assertEqual(project["blocked_task_count"], 1)
        self.assertEqual(project["rework_task_count"], 1)
        self.assertEqual(project["done_task_count"], 1)
        self.assertEqual(project["completed_task_count"], 2)
        # progress: 2/7 = 28.57... -> 29%
        self.assertEqual(project["task_progress_percent"], 29)

    def test_backlog_summary_with_data(self):
        """バックログ概要が正しくカウントされる"""
        _insert_project(self.conn, "PJ_A", "Project A")
        _insert_backlog_item(self.conn, "BL_01", "PJ_A", "BL1", "TODO", "High")
        _insert_backlog_item(self.conn, "BL_02", "PJ_A", "BL2", "TODO", "Medium")
        _insert_backlog_item(self.conn, "BL_03", "PJ_A", "BL3", "IN_PROGRESS", "High")
        _insert_backlog_item(self.conn, "BL_04", "PJ_A", "BL4", "DONE", "Low")

        result = get_unified_status(self.conn, project_id="PJ_A")
        backlog = result["backlog_summary"]

        self.assertEqual(backlog["total_items"], 4)
        self.assertEqual(backlog["todo_count"], 2)
        self.assertEqual(backlog["in_progress_count"], 1)
        self.assertEqual(backlog["high_priority_count"], 2)
        # 単一プロジェクトモードではproject_active_countがある
        self.assertIn("project_active_count", backlog)
        # TODO + IN_PROGRESS = 3
        self.assertEqual(backlog["project_active_count"], 3)

    def test_backlog_summary_by_project_in_active_mode(self):
        """アクティブモードでバックログのプロジェクト別集計"""
        _insert_project(self.conn, "PJ_A", "Project A")
        _insert_project(self.conn, "PJ_B", "Project B")
        _insert_backlog_item(self.conn, "BL_01", "PJ_A", "BL1", "TODO")
        _insert_backlog_item(self.conn, "BL_02", "PJ_A", "BL2", "TODO")
        _insert_backlog_item(self.conn, "BL_03", "PJ_B", "BL3", "TODO")

        result = get_active_projects_status(self.conn)
        backlog = result["backlog_summary"]

        self.assertIn("by_project", backlog)
        self.assertEqual(backlog["by_project"]["PJ_A"], 2)
        self.assertEqual(backlog["by_project"]["PJ_B"], 1)


# ============================================================
# パフォーマンステスト
# ============================================================


class TestPerformance(unittest.TestCase):
    """パフォーマンス関連テスト"""

    def setUp(self):
        self.conn = _create_test_db()

    def tearDown(self):
        self.conn.close()

    def test_query_count_is_constant_single_project(self):
        """単一プロジェクトモードでクエリ数が定数"""
        _insert_project(self.conn, "PJ_A", "Project A")
        _insert_order(self.conn, "ORDER_001", "PJ_A", "O1", "IN_PROGRESS")
        _insert_task(self.conn, "TASK_001", "ORDER_001", "PJ_A", "T1", "QUEUED")

        result = get_unified_status(self.conn, project_id="PJ_A")
        qc_small = result["metadata"]["query_count"]

        # プロジェクトにORDER/タスクを追加
        for i in range(2, 6):
            _insert_order(self.conn, f"ORDER_{i:03d}", "PJ_A", f"O{i}", "IN_PROGRESS")
            for j in range(1, 4):
                _insert_task(
                    self.conn, f"TASK_{i}_{j}", f"ORDER_{i:03d}", "PJ_A",
                    f"T{i}_{j}", "QUEUED"
                )

        result2 = get_unified_status(self.conn, project_id="PJ_A")
        qc_large = result2["metadata"]["query_count"]

        # クエリ数が同じ（定数）であることを検証
        self.assertEqual(qc_small, qc_large,
                         f"Query count should be constant: small={qc_small}, large={qc_large}")

    def test_query_count_is_constant_multi_project(self):
        """マルチプロジェクトモードでクエリ数がプロジェクト数に依存しない"""
        # 1プロジェクト
        _insert_project(self.conn, "PJ_1", "Project 1")
        _insert_order(self.conn, "ORDER_001", "PJ_1", "O1", "IN_PROGRESS")
        _insert_task(self.conn, "TASK_001", "ORDER_001", "PJ_1", "T1", "QUEUED")

        result1 = get_all_projects_status(self.conn)
        qc_1 = result1["metadata"]["query_count"]

        # 5プロジェクトに増やす
        for i in range(2, 6):
            pid = f"PJ_{i}"
            _insert_project(self.conn, pid, f"Project {i}")
            _insert_order(self.conn, f"ORDER_{i:03d}", pid, f"O{i}", "IN_PROGRESS")
            _insert_task(self.conn, f"TASK_{i:03d}", f"ORDER_{i:03d}", pid, f"T{i}", "QUEUED")

        result5 = get_all_projects_status(self.conn)
        qc_5 = result5["metadata"]["query_count"]

        # クエリ数が同じ（定数）であることを検証
        self.assertEqual(qc_1, qc_5,
                         f"Query count should be constant regardless of project count: "
                         f"1proj={qc_1}, 5proj={qc_5}")

    def test_metadata_contains_query_count(self):
        """metadataにquery_countが含まれる"""
        _insert_project(self.conn, "PJ_A", "Project A")

        result = get_unified_status(self.conn, project_id="PJ_A")

        self.assertIn("query_count", result["metadata"])
        self.assertIsInstance(result["metadata"]["query_count"], int)
        self.assertGreater(result["metadata"]["query_count"], 0)


# ============================================================
# ORDER・タスク統計の正確性テスト
# ============================================================


class TestOrderStatistics(unittest.TestCase):
    """ORDER統計の正確性テスト"""

    def setUp(self):
        self.conn = _create_test_db()

    def tearDown(self):
        self.conn.close()

    def test_order_status_counts(self):
        """ORDER統計が正しい"""
        _insert_project(self.conn, "PJ_A", "Project A")
        _insert_order(self.conn, "ORDER_001", "PJ_A", "Planning", "PLANNING")
        _insert_order(self.conn, "ORDER_002", "PJ_A", "In Progress", "IN_PROGRESS")
        _insert_order(self.conn, "ORDER_003", "PJ_A", "Review", "REVIEW")
        _insert_order(self.conn, "ORDER_004", "PJ_A", "Completed", "COMPLETED")
        _insert_order(self.conn, "ORDER_005", "PJ_A", "Draft", "DRAFT")

        result = get_unified_status(self.conn, project_id="PJ_A")
        project = result["projects"][0]

        self.assertEqual(project["order_count"], 5)
        self.assertEqual(project["active_order_count"], 3)  # PLANNING + IN_PROGRESS + REVIEW
        self.assertEqual(project["completed_order_count"], 1)
        self.assertEqual(project["draft_order_count"], 1)

    def test_active_orders_sorted_correctly(self):
        """アクティブORDERがステータス→優先度順でソートされている"""
        _insert_project(self.conn, "PJ_A", "Project A")
        _insert_order(self.conn, "ORDER_P", "PJ_A", "Planning P1", "PLANNING", "P1")
        _insert_order(self.conn, "ORDER_I", "PJ_A", "InProgress P0", "IN_PROGRESS", "P0")
        _insert_order(self.conn, "ORDER_R", "PJ_A", "Review P2", "REVIEW", "P2")

        result = get_unified_status(self.conn, project_id="PJ_A")
        active_orders = result["projects"][0]["active_orders"]

        # IN_PROGRESS -> REVIEW -> PLANNING の順序
        self.assertEqual(active_orders[0]["id"], "ORDER_I")
        self.assertEqual(active_orders[1]["id"], "ORDER_R")
        self.assertEqual(active_orders[2]["id"], "ORDER_P")

    def test_order_progress_percent(self):
        """ORDER単位の進捗率が正しい"""
        _insert_project(self.conn, "PJ_A", "Project A")
        _insert_order(self.conn, "ORDER_001", "PJ_A", "Order 1", "IN_PROGRESS")
        _insert_task(self.conn, "TASK_001", "ORDER_001", "PJ_A", "T1", "COMPLETED")
        _insert_task(self.conn, "TASK_002", "ORDER_001", "PJ_A", "T2", "COMPLETED")
        _insert_task(self.conn, "TASK_003", "ORDER_001", "PJ_A", "T3", "QUEUED")
        _insert_task(self.conn, "TASK_004", "ORDER_001", "PJ_A", "T4", "IN_PROGRESS")

        result = get_unified_status(self.conn, project_id="PJ_A")
        order = result["projects"][0]["active_orders"][0]

        # 2/4 = 50%
        self.assertEqual(order["progress_percent"], 50)
        self.assertEqual(order["task_count"], 4)
        self.assertEqual(order["completed_task_count"], 2)


# ============================================================
# プロジェクトソート順テスト
# ============================================================


class TestProjectSortOrder(unittest.TestCase):
    """プロジェクトのソート順テスト"""

    def setUp(self):
        self.conn = _create_test_db()

    def tearDown(self):
        self.conn.close()

    def test_projects_sorted_by_status(self):
        """プロジェクトがステータス順にソートされている"""
        # 逆順で挿入
        _insert_project(self.conn, "PJ_COMPLETED", "Completed", "COMPLETED")
        _insert_project(self.conn, "PJ_PLANNING", "Planning", "PLANNING")
        _insert_project(self.conn, "PJ_PROGRESS", "In Progress", "IN_PROGRESS")

        result = get_all_projects_status(self.conn)
        project_ids = [p["id"] for p in result["projects"]]

        # IN_PROGRESS -> PLANNING -> COMPLETED の順
        self.assertEqual(project_ids[0], "PJ_PROGRESS")
        self.assertEqual(project_ids[1], "PJ_PLANNING")
        self.assertEqual(project_ids[2], "PJ_COMPLETED")


# ============================================================
# 複合シナリオテスト
# ============================================================


class TestComplexScenarios(unittest.TestCase):
    """複合シナリオテスト"""

    def setUp(self):
        self.conn = _create_test_db()

    def tearDown(self):
        self.conn.close()

    def test_multiple_projects_with_mixed_data(self):
        """複数プロジェクトに混在するデータの正確性"""
        # PJ_A: アクティブ、ORDER 2つ、タスク複数
        _insert_project(self.conn, "PJ_A", "Project A", "IN_PROGRESS")
        _insert_order(self.conn, "ORDER_A1", "PJ_A", "A Order 1", "IN_PROGRESS")
        _insert_order(self.conn, "ORDER_A2", "PJ_A", "A Order 2", "COMPLETED")
        _insert_task(self.conn, "TASK_A1", "ORDER_A1", "PJ_A", "A Task 1", "QUEUED")
        _insert_task(self.conn, "TASK_A2", "ORDER_A1", "PJ_A", "A Task 2", "COMPLETED")

        # PJ_B: アクティブ、DRAFTオーダーのみ
        _insert_project(self.conn, "PJ_B", "Project B", "PLANNING")
        _insert_order(self.conn, "ORDER_B1", "PJ_B", "B Draft 1", "DRAFT")

        result = get_all_projects_status(self.conn)

        # PJ_Aの確認
        pj_a = next(p for p in result["projects"] if p["id"] == "PJ_A")
        self.assertEqual(pj_a["order_count"], 2)
        self.assertEqual(pj_a["active_order_count"], 1)
        self.assertEqual(pj_a["task_count"], 2)

        # PJ_Bの確認
        pj_b = next(p for p in result["projects"] if p["id"] == "PJ_B")
        self.assertEqual(pj_b["order_count"], 1)
        self.assertEqual(pj_b["draft_order_count"], 1)
        self.assertEqual(pj_b["task_count"], 0)

        # PJ_A のタスクが PJ_B のカウントに混ざらないこと
        self.assertEqual(pj_b["completed_task_count"], 0)

    def test_format_full_scenario(self):
        """完全なシナリオでフォーマットが正しく生成される"""
        _insert_project(self.conn, "PJ_A", "Project Alpha")
        _insert_order(self.conn, "ORDER_001", "PJ_A", "Feature Order", "IN_PROGRESS", "P0")
        _insert_order(self.conn, "ORDER_D01", "PJ_A", "Draft Order", "DRAFT")
        _insert_task(self.conn, "TASK_001", "ORDER_001", "PJ_A", "Implement Feature", "IN_PROGRESS", assignee="Worker A")
        _insert_task(self.conn, "TASK_002", "ORDER_001", "PJ_A", "Write Tests", "QUEUED")
        _insert_backlog_item(self.conn, "BL_001", "PJ_A", "Future Work", "TODO", "High")

        result = get_unified_status(self.conn, project_id="PJ_A")
        output = format_human_readable(result)

        # 一連の出力に全要素が含まれるか総合チェック
        checks = [
            "Project Alpha",
            "IN_PROGRESS",
            "ORDER_001",
            "Feature Order",
            "P0",
            "TASK_001",
            "Implement Feature",
            "Worker A",
            "TASK_002",
            "Write Tests",
            "DRAFT ORDER",
            "ORDER_D01",
            "Draft Order",
            "バックログ概要",
        ]
        for check in checks:
            self.assertIn(check, output, f"Expected '{check}' in output")


# ============================================================
# is_activeカラムなしの互換性テスト
# ============================================================


class TestIsActiveColumnMissing(unittest.TestCase):
    """is_activeカラムが存在しないDBへの互換性テスト"""

    def setUp(self):
        self.conn = _create_test_db()

    def tearDown(self):
        self.conn.close()

    def test_no_is_active_column(self):
        """is_activeカラムがなくてもエラーにならない"""
        # is_activeカラムを削除するため、テーブルを再作成
        # SQLiteはDROP COLUMNを完全サポートしないため、テーブルを再作成
        self.conn.execute("PRAGMA foreign_keys = OFF")
        self.conn.execute("""
            CREATE TABLE projects_backup AS
            SELECT id, name, path, status, current_order_id, created_at, updated_at
            FROM projects
        """)
        self.conn.execute("DROP TABLE projects")
        self.conn.execute("""
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'INITIAL',
                current_order_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.execute("INSERT INTO projects SELECT * FROM projects_backup")
        self.conn.execute("DROP TABLE projects_backup")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.commit()

        # プロジェクトを挿入（is_activeカラムなし）
        self.conn.execute(
            "INSERT INTO projects (id, name, path, status) VALUES (?, ?, ?, ?)",
            ("PJ_A", "Project A", "/test", "IN_PROGRESS"),
        )
        self.conn.commit()

        # エラーなく動作する
        result = get_unified_status(self.conn)

        self.assertEqual(len(result["projects"]), 1)
        # is_activeがTrueにデフォルト設定される
        self.assertTrue(result["projects"][0].get("is_active", True))


def run_tests():
    """テスト実行"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        TestSingleProjectMode,
        TestActiveProjectsMode,
        TestAllProjectsMode,
        TestJsonOutput,
        TestHumanReadableFormat,
        TestBoundaryConditions,
        TestPerformance,
        TestOrderStatistics,
        TestProjectSortOrder,
        TestComplexScenarios,
        TestIsActiveColumnMissing,
    ]

    for tc in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(tc))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

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
