"""
AI PM Framework - E2Eテスト Phase 2

全体の統合テスト：
- タスク実行→レビュー→完了の全フロー
- エラーケース（不正遷移、ロールバック）
- パフォーマンステスト
"""

import pytest
import sqlite3
from pathlib import Path
from datetime import datetime
import sys
import tempfile
import os
import time

# パス設定
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.db import (
    get_connection,
    transaction,
    execute_query,
    fetch_one,
    fetch_all,
    init_database,
    DatabaseError,
)
from utils.transition import (
    validate_transition,
    record_transition,
    TransitionError,
)
from config import get_db_config, DBConfig, set_db_config


@pytest.fixture
def test_db():
    """テスト用データベースをセットアップ"""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(db_path)

    config = DBConfig(
        db_path=db_path,
        schema_path=get_db_config().schema_path,
    )
    set_db_config(config)

    init_database(db_path)

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

    conn.commit()

    yield conn, db_path

    conn.close()
    try:
        os.unlink(db_path)
    except:
        pass


class TestTC001_TaskExecutionFlowComplete:
    """TC-001: タスク作成→割当→実行→完了→レビュー承認"""

    def test_full_task_lifecycle(self, test_db):
        """タスクのライフサイクル全体をテスト"""
        conn, _ = test_db

        # 1. タスク作成（PM）
        execute_query(
            conn,
            """
            INSERT INTO tasks (id, order_id, title, status)
            VALUES ('TASK_TC001', 'ORDER_001', 'Test Task TC001', 'QUEUED')
            """
        )
        record_transition(conn, "task", "TASK_TC001", None, "QUEUED", "PM")
        conn.commit()

        task = fetch_one(conn, "SELECT * FROM tasks WHERE id = 'TASK_TC001'")
        assert task["status"] == "QUEUED"

        # 2. タスク開始（Worker）
        validate_transition(conn, "task", "QUEUED", "IN_PROGRESS", "Worker")
        execute_query(
            conn,
            "UPDATE tasks SET status = 'IN_PROGRESS', assignee = 'Worker A' WHERE id = 'TASK_TC001'"
        )
        record_transition(conn, "task", "TASK_TC001", "QUEUED", "IN_PROGRESS", "Worker A")
        conn.commit()

        task = fetch_one(conn, "SELECT * FROM tasks WHERE id = 'TASK_TC001'")
        assert task["status"] == "IN_PROGRESS"
        assert task["assignee"] == "Worker A"

        # 3. タスク完了（Worker）
        validate_transition(conn, "task", "IN_PROGRESS", "DONE", "Worker")
        execute_query(
            conn,
            "UPDATE tasks SET status = 'DONE' WHERE id = 'TASK_TC001'"
        )
        record_transition(conn, "task", "TASK_TC001", "IN_PROGRESS", "DONE", "Worker A")
        conn.commit()

        task = fetch_one(conn, "SELECT * FROM tasks WHERE id = 'TASK_TC001'")
        assert task["status"] == "DONE"

        # 4. レビューキューに追加
        execute_query(
            conn,
            """
            INSERT INTO review_queue (task_id, status, priority)
            VALUES ('TASK_TC001', 'PENDING', 'P1')
            """
        )
        record_transition(conn, "review", "TASK_TC001", None, "PENDING", "Worker A")
        conn.commit()

        # 5. PMレビュー開始
        validate_transition(conn, "review", "PENDING", "IN_REVIEW", "PM")
        execute_query(
            conn,
            "UPDATE review_queue SET status = 'IN_REVIEW', reviewer = 'PM' WHERE task_id = 'TASK_TC001'"
        )
        record_transition(conn, "review", "TASK_TC001", "PENDING", "IN_REVIEW", "PM")
        conn.commit()

        # 6. レビュー承認
        validate_transition(conn, "review", "IN_REVIEW", "APPROVED", "PM")
        execute_query(
            conn,
            "UPDATE review_queue SET status = 'APPROVED' WHERE task_id = 'TASK_TC001'"
        )
        record_transition(conn, "review", "TASK_TC001", "IN_REVIEW", "APPROVED", "PM")

        validate_transition(conn, "task", "DONE", "COMPLETED", "PM")
        execute_query(
            conn,
            "UPDATE tasks SET status = 'COMPLETED' WHERE id = 'TASK_TC001'"
        )
        record_transition(conn, "task", "TASK_TC001", "DONE", "COMPLETED", "PM")
        conn.commit()

        # 最終確認
        task = fetch_one(conn, "SELECT * FROM tasks WHERE id = 'TASK_TC001'")
        assert task["status"] == "COMPLETED"

        review = fetch_one(conn, "SELECT * FROM review_queue WHERE task_id = 'TASK_TC001'")
        assert review["status"] == "APPROVED"


class TestTC002_TaskReworkFlow:
    """TC-002: タスク差し戻し→修正→再提出→承認"""

    def test_rework_flow(self, test_db):
        """差し戻しフローをテスト"""
        conn, _ = test_db

        # タスク作成 → 実行 → 完了
        execute_query(
            conn,
            """
            INSERT INTO tasks (id, order_id, title, status, assignee)
            VALUES ('TASK_TC002', 'ORDER_001', 'Test Task TC002', 'DONE', 'Worker A')
            """
        )
        execute_query(
            conn,
            """
            INSERT INTO review_queue (task_id, status, priority)
            VALUES ('TASK_TC002', 'PENDING', 'P1')
            """
        )
        conn.commit()

        # PMレビュー → 差し戻し
        validate_transition(conn, "task", "DONE", "REWORK", "PM")
        execute_query(
            conn,
            "UPDATE tasks SET status = 'REWORK' WHERE id = 'TASK_TC002'"
        )
        record_transition(conn, "task", "TASK_TC002", "DONE", "REWORK", "PM", "品質不足")

        validate_transition(conn, "review", "PENDING", "IN_REVIEW", "PM")
        execute_query(
            conn,
            "UPDATE review_queue SET status = 'REJECTED', reviewer = 'PM' WHERE task_id = 'TASK_TC002'"
        )
        record_transition(conn, "review", "TASK_TC002", "PENDING", "REJECTED", "PM")
        conn.commit()

        task = fetch_one(conn, "SELECT * FROM tasks WHERE id = 'TASK_TC002'")
        assert task["status"] == "REWORK"

        # Worker修正 → 再完了
        validate_transition(conn, "task", "REWORK", "DONE", "Worker")
        execute_query(
            conn,
            "UPDATE tasks SET status = 'DONE' WHERE id = 'TASK_TC002'"
        )
        record_transition(conn, "task", "TASK_TC002", "REWORK", "DONE", "Worker A", "修正完了")
        conn.commit()

        # 再提出（優先度P0）
        execute_query(
            conn,
            "UPDATE review_queue SET status = 'PENDING', priority = 'P0' WHERE task_id = 'TASK_TC002'"
        )
        record_transition(conn, "review", "TASK_TC002", "REJECTED", "PENDING", "Worker A")
        conn.commit()

        review = fetch_one(conn, "SELECT * FROM review_queue WHERE task_id = 'TASK_TC002'")
        assert review["priority"] == "P0"

        # 再レビュー → 承認
        validate_transition(conn, "task", "DONE", "COMPLETED", "PM")
        execute_query(
            conn,
            "UPDATE tasks SET status = 'COMPLETED' WHERE id = 'TASK_TC002'"
        )
        execute_query(
            conn,
            "UPDATE review_queue SET status = 'APPROVED' WHERE task_id = 'TASK_TC002'"
        )
        conn.commit()

        task = fetch_one(conn, "SELECT * FROM tasks WHERE id = 'TASK_TC002'")
        assert task["status"] == "COMPLETED"


class TestTC003_InvalidTransitionRollback:
    """TC-003: 不正遷移検出→エラー→ロールバック"""

    def test_invalid_transition_detection(self, test_db):
        """不正な状態遷移が検出されること"""
        conn, _ = test_db

        # タスク作成（QUEUED状態）
        execute_query(
            conn,
            """
            INSERT INTO tasks (id, order_id, title, status)
            VALUES ('TASK_TC003', 'ORDER_001', 'Test Task TC003', 'QUEUED')
            """
        )
        conn.commit()

        # QUEUED → COMPLETED は不正（直接完了は不可）
        with pytest.raises(TransitionError):
            validate_transition(conn, "task", "QUEUED", "COMPLETED", "Worker")

    def test_rollback_on_error(self, test_db):
        """エラー時のロールバック"""
        conn, _ = test_db
        from rollback.undo import undo_last_operation

        # タスク作成 → 開始
        execute_query(
            conn,
            """
            INSERT INTO tasks (id, order_id, title, status)
            VALUES ('TASK_TC003B', 'ORDER_001', 'Test Task TC003B', 'QUEUED')
            """
        )
        conn.commit()

        execute_query(
            conn,
            "UPDATE tasks SET status = 'IN_PROGRESS' WHERE id = 'TASK_TC003B'"
        )
        record_transition(conn, "task", "TASK_TC003B", "QUEUED", "IN_PROGRESS", "Worker A")
        conn.commit()

        # ロールバック実行
        result = undo_last_operation(conn, render_after=False)
        assert result["result"]["reverted_to"] == "QUEUED"

        task = fetch_one(conn, "SELECT * FROM tasks WHERE id = 'TASK_TC003B'")
        assert task["status"] == "QUEUED"


class TestTC004_BacklogToOrderConversion:
    """TC-004: BACKLOG→ORDER変換→タスク発行→実行"""

    def test_backlog_conversion_flow(self, test_db):
        """BACKLOG→ORDER変換フロー"""
        conn, _ = test_db

        # BACKLOG作成
        execute_query(
            conn,
            """
            INSERT INTO backlog_items (id, project_id, title, priority, status)
            VALUES ('BACKLOG_001', 'TEST_PJ', 'New Feature', 'High', 'TODO')
            """
        )
        record_transition(conn, "backlog", "BACKLOG_001", None, "TODO", "PM")
        conn.commit()

        # BACKLOG → ORDER変換
        execute_query(
            conn,
            """
            INSERT INTO orders (id, project_id, title, status)
            VALUES ('ORDER_002', 'TEST_PJ', 'New Feature Order', 'PLANNING')
            """
        )
        record_transition(conn, "order", "ORDER_002", None, "PLANNING", "PM")

        validate_transition(conn, "backlog", "TODO", "IN_PROGRESS", "PM")
        execute_query(
            conn,
            """
            UPDATE backlog_items
            SET status = 'IN_PROGRESS', related_order_id = 'ORDER_002'
            WHERE id = 'BACKLOG_001'
            """
        )
        record_transition(conn, "backlog", "BACKLOG_001", "TODO", "IN_PROGRESS", "PM")
        conn.commit()

        backlog = fetch_one(conn, "SELECT * FROM backlog_items WHERE id = 'BACKLOG_001'")
        assert backlog["status"] == "IN_PROGRESS"
        assert backlog["related_order_id"] == "ORDER_002"

        # タスク発行
        execute_query(
            conn,
            """
            INSERT INTO tasks (id, order_id, title, status)
            VALUES ('TASK_TC004', 'ORDER_002', 'Task from Backlog', 'QUEUED')
            """
        )
        record_transition(conn, "task", "TASK_TC004", None, "QUEUED", "PM")

        # ORDER開始
        validate_transition(conn, "order", "PLANNING", "IN_PROGRESS", "PM")
        execute_query(
            conn,
            "UPDATE orders SET status = 'IN_PROGRESS' WHERE id = 'ORDER_002'"
        )
        record_transition(conn, "order", "ORDER_002", "PLANNING", "IN_PROGRESS", "PM")
        conn.commit()

        order = fetch_one(conn, "SELECT * FROM orders WHERE id = 'ORDER_002'")
        assert order["status"] == "IN_PROGRESS"


class TestTC005_ParallelTaskExecution:
    """TC-005: 複数タスク並行実行→レビュー→完了"""

    def test_parallel_tasks(self, test_db):
        """複数タスクの並行実行"""
        conn, _ = test_db

        # 3つのタスクを作成
        for i in range(1, 4):
            execute_query(
                conn,
                f"""
                INSERT INTO tasks (id, order_id, title, status)
                VALUES ('TASK_PAR_{i}', 'ORDER_001', 'Parallel Task {i}', 'QUEUED')
                """
            )
            record_transition(conn, "task", f"TASK_PAR_{i}", None, "QUEUED", "PM")
        conn.commit()

        # 並行で開始（Worker A, B, C）
        workers = ["Worker A", "Worker B", "Worker C"]
        for i, worker in enumerate(workers, 1):
            execute_query(
                conn,
                f"""
                UPDATE tasks
                SET status = 'IN_PROGRESS', assignee = '{worker}'
                WHERE id = 'TASK_PAR_{i}'
                """
            )
            record_transition(conn, "task", f"TASK_PAR_{i}", "QUEUED", "IN_PROGRESS", worker)
        conn.commit()

        # 全て実行中であることを確認
        in_progress = fetch_all(
            conn,
            "SELECT * FROM tasks WHERE status = 'IN_PROGRESS' AND id LIKE 'TASK_PAR_%'"
        )
        assert len(in_progress) == 3

        # 順次完了
        for i in range(1, 4):
            execute_query(
                conn,
                f"UPDATE tasks SET status = 'DONE' WHERE id = 'TASK_PAR_{i}'"
            )
            execute_query(
                conn,
                f"""
                INSERT INTO review_queue (task_id, status, priority)
                VALUES ('TASK_PAR_{i}', 'PENDING', 'P1')
                """
            )
        conn.commit()

        # レビュー承認
        for i in range(1, 4):
            execute_query(
                conn,
                f"UPDATE tasks SET status = 'COMPLETED' WHERE id = 'TASK_PAR_{i}'"
            )
            execute_query(
                conn,
                f"UPDATE review_queue SET status = 'APPROVED' WHERE task_id = 'TASK_PAR_{i}'"
            )
        conn.commit()

        completed = fetch_all(
            conn,
            "SELECT * FROM tasks WHERE status = 'COMPLETED' AND id LIKE 'TASK_PAR_%'"
        )
        assert len(completed) == 3


class TestTC006_OrderHoldAndResume:
    """TC-006: ORDER一時停止→再開→完了"""

    def test_order_hold_resume(self, test_db):
        """ORDER一時停止と再開"""
        conn, _ = test_db

        order = fetch_one(conn, "SELECT * FROM orders WHERE id = 'ORDER_001'")
        assert order["status"] == "IN_PROGRESS"

        # 一時停止
        validate_transition(conn, "order", "IN_PROGRESS", "ON_HOLD", "PM")
        execute_query(
            conn,
            "UPDATE orders SET status = 'ON_HOLD' WHERE id = 'ORDER_001'"
        )
        record_transition(conn, "order", "ORDER_001", "IN_PROGRESS", "ON_HOLD", "PM", "リソース不足")
        conn.commit()

        order = fetch_one(conn, "SELECT * FROM orders WHERE id = 'ORDER_001'")
        assert order["status"] == "ON_HOLD"

        # 再開
        validate_transition(conn, "order", "ON_HOLD", "IN_PROGRESS", "PM")
        execute_query(
            conn,
            "UPDATE orders SET status = 'IN_PROGRESS' WHERE id = 'ORDER_001'"
        )
        record_transition(conn, "order", "ORDER_001", "ON_HOLD", "IN_PROGRESS", "PM", "リソース確保")
        conn.commit()

        order = fetch_one(conn, "SELECT * FROM orders WHERE id = 'ORDER_001'")
        assert order["status"] == "IN_PROGRESS"


class TestTC007_UndoOperation:
    """TC-007: ロールバック（直前操作取り消し）"""

    def test_undo_single_operation(self, test_db):
        """単一操作の取り消し"""
        from rollback.undo import undo_last_operation

        conn, _ = test_db

        # タスク作成→開始
        execute_query(
            conn,
            """
            INSERT INTO tasks (id, order_id, title, status)
            VALUES ('TASK_UNDO', 'ORDER_001', 'Undo Test', 'QUEUED')
            """
        )
        conn.commit()

        execute_query(
            conn,
            "UPDATE tasks SET status = 'IN_PROGRESS' WHERE id = 'TASK_UNDO'"
        )
        record_transition(conn, "task", "TASK_UNDO", "QUEUED", "IN_PROGRESS", "Worker A")
        conn.commit()

        # 取り消し
        result = undo_last_operation(conn, render_after=False)
        assert result["result"]["reverted_to"] == "QUEUED"

        task = fetch_one(conn, "SELECT * FROM tasks WHERE id = 'TASK_UNDO'")
        assert task["status"] == "QUEUED"


class TestTC008_RestoreToPoint:
    """TC-008: ロールバック（時点指定復元）"""

    def test_restore_to_timestamp(self, test_db):
        """時点指定復元"""
        from rollback.restore import restore_to_point

        conn, _ = test_db

        # タスク作成
        execute_query(
            conn,
            """
            INSERT INTO tasks (id, order_id, title, status)
            VALUES ('TASK_RESTORE', 'ORDER_001', 'Restore Test', 'QUEUED')
            """
        )
        record_transition(conn, "task", "TASK_RESTORE", None, "QUEUED", "PM")
        conn.commit()

        # 復元ポイント
        restore_point = datetime.now().isoformat()

        # 複数の変更
        execute_query(
            conn,
            "UPDATE tasks SET status = 'IN_PROGRESS' WHERE id = 'TASK_RESTORE'"
        )
        record_transition(conn, "task", "TASK_RESTORE", "QUEUED", "IN_PROGRESS", "Worker A")

        execute_query(
            conn,
            "UPDATE tasks SET status = 'DONE' WHERE id = 'TASK_RESTORE'"
        )
        record_transition(conn, "task", "TASK_RESTORE", "IN_PROGRESS", "DONE", "Worker A")
        conn.commit()

        task = fetch_one(conn, "SELECT * FROM tasks WHERE id = 'TASK_RESTORE'")
        assert task["status"] == "DONE"

        # 復元
        result = restore_to_point(conn, timestamp=restore_point, render_after=False)
        assert result["undone_count"] >= 2

        task = fetch_one(conn, "SELECT * FROM tasks WHERE id = 'TASK_RESTORE'")
        assert task["status"] == "QUEUED"


class TestTC009_AutoRollbackOnError:
    """TC-009: エラー発生→自動ロールバック"""

    def test_transaction_rollback(self, test_db):
        """トランザクションエラー時の自動ロールバック"""
        conn, _ = test_db

        task_before = fetch_one(conn, "SELECT status FROM tasks WHERE id LIKE 'TASK%'")

        # 不正なSQL（外部キー制約違反）でエラー
        try:
            with transaction(conn):
                execute_query(
                    conn,
                    """
                    INSERT INTO tasks (id, order_id, title, status)
                    VALUES ('TASK_ERR', 'NONEXISTENT_ORDER', 'Error Test', 'QUEUED')
                    """
                )
        except DatabaseError:
            pass  # 期待通りのエラー

        # ロールバックされていることを確認
        task_after = fetch_one(conn, "SELECT * FROM tasks WHERE id = 'TASK_ERR'")
        assert task_after is None  # 挿入されていない


class TestTC010_PerformanceTest:
    """TC-010: パフォーマンス（100操作連続実行）"""

    def test_100_operations_performance(self, test_db):
        """100操作の連続実行パフォーマンス"""
        conn, _ = test_db

        # 100タスクを一括作成
        start_time = time.time()

        for i in range(100):
            execute_query(
                conn,
                f"""
                INSERT INTO tasks (id, order_id, title, status)
                VALUES ('TASK_PERF_{i:03d}', 'ORDER_001', 'Perf Test {i}', 'QUEUED')
                """
            )
            record_transition(conn, "task", f"TASK_PERF_{i:03d}", None, "QUEUED", "PM")

        conn.commit()
        create_time = time.time() - start_time

        # 100タスクのステータス更新
        start_time = time.time()

        for i in range(100):
            execute_query(
                conn,
                f"UPDATE tasks SET status = 'IN_PROGRESS' WHERE id = 'TASK_PERF_{i:03d}'"
            )
            record_transition(
                conn, "task", f"TASK_PERF_{i:03d}",
                "QUEUED", "IN_PROGRESS", "Worker A"
            )

        conn.commit()
        update_time = time.time() - start_time

        # パフォーマンス基準: 100操作が10秒以内（1操作あたり100ms以下）
        assert create_time < 10.0, f"Create time too slow: {create_time:.2f}s"
        assert update_time < 10.0, f"Update time too slow: {update_time:.2f}s"

        # 平均時間
        avg_create = create_time / 100 * 1000  # ms
        avg_update = update_time / 100 * 1000  # ms

        print(f"\nPerformance Results:")
        print(f"  Create 100 tasks: {create_time:.3f}s (avg: {avg_create:.1f}ms/op)")
        print(f"  Update 100 tasks: {update_time:.3f}s (avg: {avg_update:.1f}ms/op)")

        # 基準: 1操作100ms以下
        assert avg_create < 100, f"Average create time too slow: {avg_create:.1f}ms"
        assert avg_update < 100, f"Average update time too slow: {avg_update:.1f}ms"

    def test_query_performance(self, test_db):
        """クエリパフォーマンス"""
        conn, _ = test_db

        # テストデータ作成
        for i in range(50):
            execute_query(
                conn,
                f"""
                INSERT INTO tasks (id, order_id, title, status)
                VALUES ('TASK_QUERY_{i:03d}', 'ORDER_001', 'Query Test {i}',
                        CASE WHEN {i} % 3 = 0 THEN 'QUEUED'
                             WHEN {i} % 3 = 1 THEN 'IN_PROGRESS'
                             ELSE 'DONE' END)
                """
            )
        conn.commit()

        # クエリ100回実行
        start_time = time.time()

        for _ in range(100):
            fetch_all(conn, "SELECT * FROM tasks WHERE status = 'IN_PROGRESS'")

        query_time = time.time() - start_time
        avg_query = query_time / 100 * 1000  # ms

        print(f"\nQuery Performance:")
        print(f"  100 SELECT queries: {query_time:.3f}s (avg: {avg_query:.1f}ms/query)")

        # 基準: 1クエリ100ms以下
        assert avg_query < 100, f"Average query time too slow: {avg_query:.1f}ms"


class TestAdditionalScenarios:
    """追加シナリオテスト"""

    def test_task_dependency_flow(self, test_db):
        """タスク依存関係フロー"""
        conn, _ = test_db

        # 依存タスク作成
        execute_query(
            conn,
            """
            INSERT INTO tasks (id, order_id, title, status)
            VALUES
                ('TASK_DEP_1', 'ORDER_001', 'Dependency Task 1', 'QUEUED'),
                ('TASK_DEP_2', 'ORDER_001', 'Dependency Task 2', 'BLOCKED')
            """
        )

        # 依存関係を追加
        execute_query(
            conn,
            """
            INSERT INTO task_dependencies (task_id, depends_on_task_id)
            VALUES ('TASK_DEP_2', 'TASK_DEP_1')
            """
        )
        conn.commit()

        # TASK_DEP_1 完了
        execute_query(
            conn,
            "UPDATE tasks SET status = 'COMPLETED' WHERE id = 'TASK_DEP_1'"
        )

        # TASK_DEP_2 をQUEUEDに（依存解消）
        execute_query(
            conn,
            "UPDATE tasks SET status = 'QUEUED' WHERE id = 'TASK_DEP_2'"
        )
        conn.commit()

        task2 = fetch_one(conn, "SELECT * FROM tasks WHERE id = 'TASK_DEP_2'")
        assert task2["status"] == "QUEUED"

    def test_interrupted_task_resume(self, test_db):
        """中断タスクの再開"""
        conn, _ = test_db

        # タスク作成→開始→中断
        execute_query(
            conn,
            """
            INSERT INTO tasks (id, order_id, title, status, assignee)
            VALUES ('TASK_INT', 'ORDER_001', 'Interrupted Task', 'IN_PROGRESS', 'Worker A')
            """
        )
        conn.commit()

        # 中断
        validate_transition(conn, "task", "IN_PROGRESS", "INTERRUPTED", "Worker")
        execute_query(
            conn,
            "UPDATE tasks SET status = 'INTERRUPTED' WHERE id = 'TASK_INT'"
        )
        record_transition(conn, "task", "TASK_INT", "IN_PROGRESS", "INTERRUPTED", "Worker A", "セッション切断")
        conn.commit()

        task = fetch_one(conn, "SELECT * FROM tasks WHERE id = 'TASK_INT'")
        assert task["status"] == "INTERRUPTED"

        # 再開
        validate_transition(conn, "task", "INTERRUPTED", "IN_PROGRESS", "Worker")
        execute_query(
            conn,
            "UPDATE tasks SET status = 'IN_PROGRESS' WHERE id = 'TASK_INT'"
        )
        record_transition(conn, "task", "TASK_INT", "INTERRUPTED", "IN_PROGRESS", "Worker A", "セッション再開")
        conn.commit()

        task = fetch_one(conn, "SELECT * FROM tasks WHERE id = 'TASK_INT'")
        assert task["status"] == "IN_PROGRESS"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
