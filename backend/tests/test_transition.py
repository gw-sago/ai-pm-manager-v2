"""
AI PM Framework - 状態遷移ユーティリティテスト

utils/transition.py の機能をテスト。
"""

import sqlite3
import tempfile
from pathlib import Path
import sys

# 親ディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from aipm_db.utils.db import get_connection, close_connection, init_database
from aipm_db.utils.transition import (
    is_transition_allowed,
    validate_transition,
    get_allowed_transitions,
    get_all_transitions,
    can_worker_execute,
    can_pm_execute,
    can_start_task,
    can_complete_task,
    can_approve_task,
    can_reject_task,
    record_transition,
    TransitionError,
)
from aipm_db.config import get_db_config


def setup_test_db():
    """テスト用DBセットアップ"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    schema_path = get_db_config().schema_path
    if schema_path.exists():
        init_database(db_path, schema_path)

    return db_path


def test_is_transition_allowed():
    """遷移許可チェックテスト"""
    print("Test: is_transition_allowed")

    db_path = setup_test_db()
    try:
        conn = get_connection(db_path)

        # タスク: QUEUED → IN_PROGRESS (Worker可能)
        assert is_transition_allowed(conn, "task", "QUEUED", "IN_PROGRESS", "Worker")

        # タスク: IN_PROGRESS → DONE (Worker可能)
        assert is_transition_allowed(conn, "task", "IN_PROGRESS", "DONE", "Worker")

        # タスク: DONE → COMPLETED (PM可能)
        assert is_transition_allowed(conn, "task", "DONE", "COMPLETED", "PM")

        # タスク: DONE → REWORK (PM可能)
        assert is_transition_allowed(conn, "task", "DONE", "REWORK", "PM")

        # タスク: QUEUED → COMPLETED (不正)
        assert not is_transition_allowed(conn, "task", "QUEUED", "COMPLETED", "Worker")

        # 同一ステータスへの遷移は常に許可
        assert is_transition_allowed(conn, "task", "IN_PROGRESS", "IN_PROGRESS", "Worker")

        close_connection(conn)
        print("  PASS: Transition check works correctly")

    finally:
        db_path.unlink(missing_ok=True)


def test_validate_transition():
    """遷移検証テスト"""
    print("Test: validate_transition")

    db_path = setup_test_db()
    try:
        conn = get_connection(db_path)

        # 有効な遷移は例外なし
        validate_transition(conn, "task", "QUEUED", "IN_PROGRESS", "Worker")

        # 無効な遷移は例外発生
        try:
            validate_transition(conn, "task", "QUEUED", "COMPLETED", "Worker")
            assert False, "Should have raised TransitionError"
        except TransitionError as e:
            assert "QUEUED" in str(e)
            assert "COMPLETED" in str(e)

        close_connection(conn)
        print("  PASS: Transition validation works correctly")

    finally:
        db_path.unlink(missing_ok=True)


def test_get_allowed_transitions():
    """許可遷移取得テスト"""
    print("Test: get_allowed_transitions")

    db_path = setup_test_db()
    try:
        conn = get_connection(db_path)

        # QUEUEDからの遷移を取得
        transitions = get_allowed_transitions(conn, "task", "QUEUED", "Worker")

        # IN_PROGRESSへの遷移があるはず
        to_statuses = [t["to_status"] for t in transitions]
        assert "IN_PROGRESS" in to_statuses

        close_connection(conn)
        print("  PASS: Get allowed transitions works correctly")

    finally:
        db_path.unlink(missing_ok=True)


def test_get_all_transitions():
    """全遷移取得テスト"""
    print("Test: get_all_transitions")

    db_path = setup_test_db()
    try:
        conn = get_connection(db_path)

        # タスクの全遷移を取得
        transitions = get_all_transitions(conn, "task")

        # 複数の遷移が定義されているはず
        assert len(transitions) > 0

        # 遷移の構造を確認
        for t in transitions:
            assert "from_status" in t
            assert "to_status" in t
            assert "allowed_role" in t
            assert "description" in t

        close_connection(conn)
        print("  PASS: Get all transitions works correctly")

    finally:
        db_path.unlink(missing_ok=True)


def test_role_specific_checks():
    """役割別チェックテスト"""
    print("Test: role-specific checks")

    db_path = setup_test_db()
    try:
        conn = get_connection(db_path)

        # Workerがタスクを開始できる
        assert can_worker_execute(conn, "task", "QUEUED", "IN_PROGRESS")

        # WorkerはDONE→COMPLETEDにできない（PM権限）
        assert not can_worker_execute(conn, "task", "DONE", "COMPLETED")

        # PMはDONE→COMPLETEDにできる
        assert can_pm_execute(conn, "task", "DONE", "COMPLETED")

        close_connection(conn)
        print("  PASS: Role-specific checks work correctly")

    finally:
        db_path.unlink(missing_ok=True)


def test_task_helper_functions():
    """タスク固有ヘルパーテスト"""
    print("Test: task helper functions")

    db_path = setup_test_db()
    try:
        conn = get_connection(db_path)

        # タスク開始可能チェック
        assert can_start_task(conn, "QUEUED")
        assert not can_start_task(conn, "COMPLETED")

        # タスク完了可能チェック
        assert can_complete_task(conn, "IN_PROGRESS")
        assert not can_complete_task(conn, "QUEUED")

        # タスク承認可能チェック
        assert can_approve_task(conn, "DONE")
        assert not can_approve_task(conn, "IN_PROGRESS")

        # タスク差し戻し可能チェック
        assert can_reject_task(conn, "DONE")
        assert can_reject_task(conn, "IN_PROGRESS")
        assert not can_reject_task(conn, "QUEUED")

        close_connection(conn)
        print("  PASS: Task helper functions work correctly")

    finally:
        db_path.unlink(missing_ok=True)


def test_record_transition():
    """遷移履歴記録テスト"""
    print("Test: record_transition")

    db_path = setup_test_db()
    try:
        conn = get_connection(db_path)

        # 遷移を記録
        history_id = record_transition(
            conn,
            entity_type="task",
            entity_id="TASK_188",
            from_status="QUEUED",
            to_status="IN_PROGRESS",
            changed_by="Worker A",
            reason="タスク開始"
        )
        conn.commit()

        assert history_id > 0

        # 履歴を確認
        cursor = conn.execute(
            "SELECT * FROM change_history WHERE id = ?",
            (history_id,)
        )
        row = cursor.fetchone()

        assert row["entity_type"] == "task"
        assert row["entity_id"] == "TASK_188"
        assert row["old_value"] == "QUEUED"
        assert row["new_value"] == "IN_PROGRESS"
        assert row["changed_by"] == "Worker A"
        assert row["change_reason"] == "タスク開始"

        close_connection(conn)
        print("  PASS: Transition recording works correctly")

    finally:
        db_path.unlink(missing_ok=True)


def run_all_tests():
    """全テスト実行"""
    print("\n=== Transition Utility Tests ===\n")

    # スキーマファイルが存在しない場合はスキップ
    schema_path = get_db_config().schema_path
    if not schema_path.exists():
        print(f"SKIP: Schema file not found at {schema_path}")
        return

    test_is_transition_allowed()
    test_validate_transition()
    test_get_allowed_transitions()
    test_get_all_transitions()
    test_role_specific_checks()
    test_task_helper_functions()
    test_record_transition()

    print("\n=== All Transition tests passed ===\n")


if __name__ == "__main__":
    run_all_tests()
