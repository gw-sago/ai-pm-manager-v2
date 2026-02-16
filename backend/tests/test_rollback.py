"""
AI PM Framework - ロールバック機能テスト

undo.py と restore.py のテスト。
"""

import pytest
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import sys
import tempfile
import os

# パス設定
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.db import (
    get_connection,
    transaction,
    execute_query,
    fetch_one,
    fetch_all,
    init_database,
)
from utils.transition import record_transition
from config import get_db_config, DBConfig, set_db_config


@pytest.fixture
def test_db():
    """テスト用データベースをセットアップ"""
    # 一時ファイルを作成
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(db_path)

    # テスト用設定を適用
    config = DBConfig(
        db_path=db_path,
        schema_path=get_db_config().schema_path,
    )
    set_db_config(config)

    # スキーマを初期化
    init_database(db_path)

    # テストデータを挿入
    conn = get_connection(db_path)

    # プロジェクト
    execute_query(
        conn,
        """
        INSERT INTO projects (id, name, path, status)
        VALUES ('TEST_PJ', 'Test Project', '/test/path', 'IN_PROGRESS')
        """
    )

    # ORDER
    execute_query(
        conn,
        """
        INSERT INTO orders (id, project_id, title, status)
        VALUES ('ORDER_001', 'TEST_PJ', 'Test Order', 'IN_PROGRESS')
        """
    )

    # タスク
    execute_query(
        conn,
        """
        INSERT INTO tasks (id, order_id, title, status, assignee)
        VALUES
            ('TASK_001', 'ORDER_001', 'Task 1', 'QUEUED', NULL),
            ('TASK_002', 'ORDER_001', 'Task 2', 'IN_PROGRESS', 'Worker A'),
            ('TASK_003', 'ORDER_001', 'Task 3', 'DONE', 'Worker A')
        """
    )

    conn.commit()

    yield conn, db_path

    # クリーンアップ
    conn.close()
    try:
        os.unlink(db_path)
    except:
        pass


class TestUndo:
    """Undo機能のテスト"""

    def test_get_last_operation_no_history(self, test_db):
        """操作履歴がない場合"""
        from rollback.undo import get_last_operation

        conn, _ = test_db
        result = get_last_operation(conn)
        assert result is None

    def test_get_last_operation_with_history(self, test_db):
        """操作履歴がある場合"""
        from rollback.undo import get_last_operation, Operation

        conn, _ = test_db

        # 操作履歴を追加
        record_transition(
            conn, "task", "TASK_001", "QUEUED", "IN_PROGRESS", "Worker A"
        )
        conn.commit()

        result = get_last_operation(conn)
        assert result is not None
        assert isinstance(result, Operation)
        assert result.entity_type == "task"
        assert result.entity_id == "TASK_001"
        assert result.old_value == "QUEUED"
        assert result.new_value == "IN_PROGRESS"

    def test_get_last_operation_with_entity_filter(self, test_db):
        """エンティティ種別でフィルタリング"""
        from rollback.undo import get_last_operation

        conn, _ = test_db

        # 複数の操作履歴を追加
        record_transition(
            conn, "task", "TASK_001", "QUEUED", "IN_PROGRESS", "Worker A"
        )
        record_transition(
            conn, "order", "ORDER_001", "IN_PROGRESS", "REVIEW", "PM"
        )
        conn.commit()

        # タスクのみ取得
        result = get_last_operation(conn, entity_type="task")
        assert result.entity_type == "task"

        # ORDERのみ取得
        result = get_last_operation(conn, entity_type="order")
        assert result.entity_type == "order"

    def test_get_recent_operations(self, test_db):
        """最近の操作一覧を取得"""
        from rollback.undo import get_recent_operations

        conn, _ = test_db

        # 複数の操作履歴を追加
        for i in range(5):
            record_transition(
                conn, "task", f"TASK_00{i % 3 + 1}",
                "QUEUED", "IN_PROGRESS", f"Worker {chr(65 + i)}"
            )
        conn.commit()

        results = get_recent_operations(conn, limit=3)
        assert len(results) == 3
        # 新しい順になっていることを確認
        assert results[0].changed_by == "Worker E"

    def test_undo_last_operation_task_status(self, test_db):
        """タスクステータスの取り消し"""
        from rollback.undo import undo_last_operation

        conn, _ = test_db

        # タスクステータスを変更
        execute_query(
            conn,
            "UPDATE tasks SET status = 'IN_PROGRESS' WHERE id = 'TASK_001'"
        )
        record_transition(
            conn, "task", "TASK_001", "QUEUED", "IN_PROGRESS", "Worker A"
        )
        conn.commit()

        # 取り消し実行
        result = undo_last_operation(conn, render_after=False)

        assert result["undone"].entity_id == "TASK_001"
        assert result["result"]["reverted_from"] == "IN_PROGRESS"
        assert result["result"]["reverted_to"] == "QUEUED"

        # DBの状態を確認
        row = fetch_one(conn, "SELECT status FROM tasks WHERE id = 'TASK_001'")
        assert row["status"] == "QUEUED"

    def test_undo_no_operation(self, test_db):
        """取り消し可能な操作がない場合"""
        from rollback.undo import undo_last_operation, UndoError

        conn, _ = test_db

        with pytest.raises(UndoError, match="取り消し可能な操作がありません"):
            undo_last_operation(conn, render_after=False)

    def test_undo_records_history(self, test_db):
        """取り消し操作が履歴に記録されること"""
        from rollback.undo import undo_last_operation, get_recent_operations

        conn, _ = test_db

        # 操作実行
        execute_query(
            conn,
            "UPDATE tasks SET status = 'IN_PROGRESS' WHERE id = 'TASK_001'"
        )
        record_transition(
            conn, "task", "TASK_001", "QUEUED", "IN_PROGRESS", "Worker A"
        )
        conn.commit()

        # 取り消し前の履歴件数
        before = len(get_recent_operations(conn, limit=100))

        # 取り消し実行
        undo_last_operation(conn, render_after=False)

        # 取り消し後の履歴件数（取り消し操作が記録される）
        after = len(get_recent_operations(conn, limit=100))
        assert after == before + 1

        # 最新の履歴が取り消し操作であること
        latest = get_recent_operations(conn, limit=1)[0]
        assert latest.changed_by == "System (Undo)"


class TestRestore:
    """Restore機能のテスト"""

    def test_get_operations_after(self, test_db):
        """指定時点以降の操作を取得"""
        from rollback.restore import get_operations_after

        conn, _ = test_db

        # 操作履歴を追加
        base_time = datetime.now()

        for i in range(3):
            record_transition(
                conn, "task", f"TASK_00{i + 1}",
                "QUEUED", "IN_PROGRESS", f"Worker {chr(65 + i)}"
            )

        conn.commit()

        # 全操作を取得
        all_ops = get_operations_after(conn, "2000-01-01")
        assert len(all_ops) == 3

    def test_get_available_restore_points(self, test_db):
        """復元ポイント一覧を取得"""
        from rollback.restore import get_available_restore_points

        conn, _ = test_db

        # 操作履歴を追加
        for i in range(5):
            record_transition(
                conn, "task", f"TASK_00{i % 3 + 1}",
                "QUEUED", "IN_PROGRESS", f"Worker {chr(65 + i)}"
            )

        conn.commit()

        points = get_available_restore_points(conn, limit=10)
        assert len(points) <= 10

        # 各ポイントに必要な情報が含まれていること
        for pt in points:
            assert "timestamp" in pt
            assert "operation_count" in pt
            assert "last_entity" in pt

    def test_restore_to_point_dry_run(self, test_db):
        """復元のドライラン"""
        from rollback.restore import restore_to_point

        conn, _ = test_db

        # 操作履歴を追加
        record_transition(
            conn, "task", "TASK_001", "QUEUED", "IN_PROGRESS", "Worker A"
        )
        conn.commit()

        result = restore_to_point(
            conn,
            timestamp="2000-01-01",
            render_after=False,
            dry_run=True,
        )

        assert result["dry_run"] is True
        assert result["undone_count"] >= 1

    def test_restore_to_point_no_operations(self, test_db):
        """復元対象がない場合"""
        from rollback.restore import restore_to_point

        conn, _ = test_db

        result = restore_to_point(
            conn,
            timestamp=datetime.now().isoformat(),
            render_after=False,
        )

        assert result["undone_count"] == 0
        assert "message" in result

    def test_restore_to_point_execute(self, test_db):
        """復元の実行"""
        from rollback.restore import restore_to_point

        conn, _ = test_db

        # 操作1: TASK_001を開始
        execute_query(
            conn,
            "UPDATE tasks SET status = 'IN_PROGRESS' WHERE id = 'TASK_001'"
        )
        record_transition(
            conn, "task", "TASK_001", "QUEUED", "IN_PROGRESS", "Worker A"
        )
        conn.commit()

        # 復元ポイントの時刻を記録
        restore_point = datetime.now().isoformat()

        # 操作2: TASK_002を完了
        execute_query(
            conn,
            "UPDATE tasks SET status = 'DONE' WHERE id = 'TASK_002'"
        )
        record_transition(
            conn, "task", "TASK_002", "IN_PROGRESS", "DONE", "Worker A"
        )
        conn.commit()

        # 復元実行
        result = restore_to_point(
            conn,
            timestamp=restore_point,
            render_after=False,
        )

        assert result["undone_count"] >= 1

        # TASK_002がIN_PROGRESSに戻っていること
        row = fetch_one(conn, "SELECT status FROM tasks WHERE id = 'TASK_002'")
        assert row["status"] == "IN_PROGRESS"

    def test_restore_to_operation_id(self, test_db):
        """操作IDで復元"""
        from rollback.restore import restore_to_operation

        conn, _ = test_db

        # 操作履歴を追加
        record_transition(
            conn, "task", "TASK_001", "QUEUED", "IN_PROGRESS", "Worker A"
        )
        conn.commit()

        # 操作IDを取得
        row = fetch_one(
            conn,
            "SELECT id FROM change_history ORDER BY id DESC LIMIT 1"
        )
        op_id = row["id"]

        result = restore_to_operation(
            conn,
            operation_id=op_id,
            render_after=False,
            dry_run=True,
        )

        assert result["dry_run"] is True

    def test_restore_to_operation_not_found(self, test_db):
        """存在しない操作IDで復元"""
        from rollback.restore import restore_to_operation, RestoreError

        conn, _ = test_db

        with pytest.raises(RestoreError, match="操作ID .* が見つかりません"):
            restore_to_operation(
                conn,
                operation_id=99999,
                render_after=False,
            )


class TestRollbackIntegration:
    """ロールバック統合テスト"""

    def test_undo_multiple_operations(self, test_db):
        """複数の操作を順次取り消し"""
        from rollback.undo import undo_last_operation

        conn, _ = test_db

        # 3つの操作を実行
        operations = [
            ("TASK_001", "QUEUED", "IN_PROGRESS"),
            ("TASK_002", "IN_PROGRESS", "DONE"),
            ("TASK_003", "DONE", "COMPLETED"),
        ]

        for task_id, from_status, to_status in operations:
            execute_query(
                conn,
                f"UPDATE tasks SET status = '{to_status}' WHERE id = '{task_id}'"
            )
            record_transition(conn, "task", task_id, from_status, to_status, "Worker A")

        conn.commit()

        # 逆順で取り消し
        for i in range(3):
            result = undo_last_operation(conn, render_after=False)
            assert result["undone"] is not None

        # 全てのタスクが元の状態に戻っていること
        row = fetch_one(conn, "SELECT status FROM tasks WHERE id = 'TASK_001'")
        assert row["status"] == "QUEUED"

        row = fetch_one(conn, "SELECT status FROM tasks WHERE id = 'TASK_002'")
        assert row["status"] == "IN_PROGRESS"

        row = fetch_one(conn, "SELECT status FROM tasks WHERE id = 'TASK_003'")
        assert row["status"] == "DONE"

    def test_restore_partial_recovery(self, test_db):
        """部分復元（一部の操作のみ取り消し）"""
        from rollback.restore import restore_to_point

        conn, _ = test_db

        # 操作1
        execute_query(
            conn,
            "UPDATE tasks SET status = 'IN_PROGRESS' WHERE id = 'TASK_001'"
        )
        record_transition(
            conn, "task", "TASK_001", "QUEUED", "IN_PROGRESS", "Worker A"
        )
        conn.commit()

        # 復元ポイント
        restore_point = datetime.now().isoformat()

        # 操作2, 3
        execute_query(
            conn,
            "UPDATE tasks SET status = 'DONE' WHERE id = 'TASK_002'"
        )
        record_transition(
            conn, "task", "TASK_002", "IN_PROGRESS", "DONE", "Worker A"
        )

        execute_query(
            conn,
            "UPDATE tasks SET status = 'COMPLETED' WHERE id = 'TASK_003'"
        )
        record_transition(
            conn, "task", "TASK_003", "DONE", "COMPLETED", "PM"
        )
        conn.commit()

        # 復元
        result = restore_to_point(
            conn,
            timestamp=restore_point,
            render_after=False,
        )

        assert result["undone_count"] == 2

        # TASK_001はIN_PROGRESSのまま（復元ポイント前の操作）
        row = fetch_one(conn, "SELECT status FROM tasks WHERE id = 'TASK_001'")
        assert row["status"] == "IN_PROGRESS"

        # TASK_002, 003は元の状態に戻る
        row = fetch_one(conn, "SELECT status FROM tasks WHERE id = 'TASK_002'")
        assert row["status"] == "IN_PROGRESS"

        row = fetch_one(conn, "SELECT status FROM tasks WHERE id = 'TASK_003'")
        assert row["status"] == "DONE"


class TestRollbackCLI:
    """CLIインターフェースのテスト"""

    def test_undo_cli_help(self):
        """undoコマンドのヘルプ"""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "rollback.undo", "--help"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        assert result.returncode == 0
        assert "直前の操作を取り消す" in result.stdout

    def test_restore_cli_help(self):
        """restoreコマンドのヘルプ"""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "rollback.restore", "--help"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        assert result.returncode == 0
        assert "指定時点の状態に復元" in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
