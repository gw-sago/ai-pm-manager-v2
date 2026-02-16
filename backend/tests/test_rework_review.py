"""
AI PM Framework - REWORK→IN_PROGRESS→DONE 遷移時の reviewed_at リセット動作確認テスト

このテストでは以下を検証する:
1. REWORK→IN_PROGRESS 遷移時に reviewed_at が NULL にリセットされること
2. リセット後に DONE になった際に自動レビューが実行可能な状態になること
3. DONE→COMPLETED/REWORK の正常フロー検証
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# 親ディレクトリをパスに追加（aipm-dbディレクトリ）
_test_dir = Path(__file__).parent
_aipm_db_dir = _test_dir.parent
sys.path.insert(0, str(_aipm_db_dir))

from utils.db import (
    get_connection,
    close_connection,
    execute_query,
    fetch_one,
    transaction,
)
from utils.transition import record_transition
from config import get_db_config


def setup_test_db() -> sqlite3.Connection:
    """
    テスト用DBをメモリに作成し、schema_v2.sqlで初期化

    Returns:
        sqlite3.Connection: メモリDB接続
    """
    # メモリDBを使用（本番DBを汚さない）
    conn = sqlite3.Connection(":memory:")
    conn.row_factory = sqlite3.Row

    # PRAGMA設定
    conn.execute("PRAGMA foreign_keys = ON")

    # スキーマを読み込んで初期化（data/schema_v2.sql を使用）
    config = get_db_config()
    ai_pm_root = config.db_path.parent.parent  # data/aipm.db → data → AI_PM
    schema_path = ai_pm_root / "data" / "schema_v2.sql"

    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    schema_sql = schema_path.read_text(encoding="utf-8")

    # スキーマ適用
    conn.executescript(schema_sql)
    conn.commit()

    return conn


def create_test_project(conn, project_id: str = "test_project") -> None:
    """テストプロジェクトを作成"""
    execute_query(
        conn,
        """
        INSERT INTO projects (id, name, path, status)
        VALUES (?, ?, ?, 'INITIAL')
        """,
        (project_id, "Test Project", f"/test/{project_id}", )
    )


def create_test_order(conn, project_id: str, order_id: str = "ORDER_001") -> None:
    """テストORDERを作成"""
    execute_query(
        conn,
        """
        INSERT INTO orders (id, project_id, title, status)
        VALUES (?, ?, 'Test Order', 'IN_PROGRESS')
        """,
        (order_id, project_id)
    )


def create_test_task(
    conn,
    project_id: str,
    order_id: str,
    task_id: str,
    status: str = "QUEUED",
    reviewed_at: Optional[str] = None,
) -> None:
    """テストタスクを作成"""
    execute_query(
        conn,
        """
        INSERT INTO tasks (
            id, project_id, order_id, title, status, reviewed_at,
            created_at, updated_at
        )
        VALUES (?, ?, ?, 'Test Task', ?, ?, ?, ?)
        """,
        (
            task_id,
            project_id,
            order_id,
            status,
            reviewed_at,
            datetime.now().isoformat(),
            datetime.now().isoformat(),
        )
    )


def update_task_status(
    conn,
    project_id: str,
    task_id: str,
    from_status: str,
    to_status: str,
) -> None:
    """
    タスクのステータスを更新（task/update.py の動作を模倣）

    REWORK→IN_PROGRESS の場合は reviewed_at を NULL にリセット
    """
    updates = ["status = ?", "updated_at = ?"]
    params = [to_status, datetime.now().isoformat()]

    # REWORK → IN_PROGRESS 遷移時に reviewed_at をリセット
    # (task/update.py L155-158 の動作を再現)
    if to_status == "IN_PROGRESS" and from_status == "REWORK":
        updates.append("reviewed_at = NULL")

    # IN_PROGRESS → DONE 遷移時はstarted_atを設定（初回のみ）
    if to_status == "IN_PROGRESS" and from_status == "QUEUED":
        updates.append("started_at = ?")
        params.append(datetime.now().isoformat())

    # COMPLETED 遷移時は completed_at を設定
    if to_status == "COMPLETED":
        updates.append("completed_at = ?")
        params.append(datetime.now().isoformat())

    params.extend([task_id, project_id])

    execute_query(
        conn,
        f"UPDATE tasks SET {', '.join(updates)} WHERE id = ? AND project_id = ?",
        tuple(params)
    )

    # 状態遷移履歴を記録
    record_transition(
        conn,
        "task",
        task_id,
        from_status,
        to_status,
        "PM" if to_status in ("COMPLETED", "REWORK") else "Worker",
        "Test transition"
    )


def get_task_reviewed_at(conn, project_id: str, task_id: str) -> Optional[str]:
    """タスクの reviewed_at カラムを取得"""
    task = fetch_one(
        conn,
        "SELECT reviewed_at FROM tasks WHERE id = ? AND project_id = ?",
        (task_id, project_id)
    )
    return task["reviewed_at"] if task else None


def test_rework_in_progress_resets_reviewed_at():
    """
    テスト1: REWORK→IN_PROGRESS 遷移時に reviewed_at が NULL にリセットされることを検証
    """
    print("Test 1: REWORK→IN_PROGRESS で reviewed_at が NULL にリセットされる")

    conn = setup_test_db()
    try:
        project_id = "test_project"
        order_id = "ORDER_001"
        task_id = "TASK_001"

        # プロジェクト・ORDER・タスクを作成
        create_test_project(conn, project_id)
        create_test_order(conn, project_id, order_id)

        # タスクを DONE 状態で作成（reviewed_at に値を設定）
        reviewed_timestamp = datetime.now().isoformat()
        create_test_task(conn, project_id, order_id, task_id, "DONE", reviewed_timestamp)

        # reviewed_at が設定されていることを確認
        reviewed_at_before = get_task_reviewed_at(conn, project_id, task_id)
        assert reviewed_at_before == reviewed_timestamp, "初期値が設定されているはず"
        print(f"  ✓ 初期 reviewed_at: {reviewed_at_before}")

        # DONE → REWORK に遷移（PM差し戻し）
        update_task_status(conn, project_id, task_id, "DONE", "REWORK")
        reviewed_at_after_rework = get_task_reviewed_at(conn, project_id, task_id)
        assert reviewed_at_after_rework == reviewed_timestamp, "REWORK遷移では reviewed_at は変更されない"
        print(f"  ✓ REWORK後 reviewed_at: {reviewed_at_after_rework} (変更なし)")

        # REWORK → IN_PROGRESS に遷移（Worker再開）
        update_task_status(conn, project_id, task_id, "REWORK", "IN_PROGRESS")
        reviewed_at_after_in_progress = get_task_reviewed_at(conn, project_id, task_id)

        # reviewed_at が NULL にリセットされていることを確認
        assert reviewed_at_after_in_progress is None, \
            f"REWORK→IN_PROGRESS で reviewed_at が NULL にリセットされるべき: {reviewed_at_after_in_progress}"
        print(f"  ✓ IN_PROGRESS後 reviewed_at: NULL (リセット成功)")

        print("  PASS: reviewed_at が正常にリセットされた")

    finally:
        close_connection(conn)


def test_done_task_eligible_for_auto_review():
    """
    テスト2: reviewed_at が NULL の DONE タスクが自動レビュー対象として検出できることを検証
    """
    print("\nTest 2: reviewed_at が NULL の DONE タスクが自動レビュー対象として検出される")

    conn = setup_test_db()
    try:
        project_id = "test_project"
        order_id = "ORDER_001"

        # プロジェクト・ORDERを作成
        create_test_project(conn, project_id)
        create_test_order(conn, project_id, order_id)

        # タスク1: reviewed_at が NULL の DONE タスク（自動レビュー対象）
        task_id_1 = "TASK_001"
        create_test_task(conn, project_id, order_id, task_id_1, "DONE", None)

        # タスク2: reviewed_at が設定済みの DONE タスク（自動レビュー対象外）
        task_id_2 = "TASK_002"
        create_test_task(
            conn, project_id, order_id, task_id_2,
            "DONE", datetime.now().isoformat()
        )

        # タスク3: IN_PROGRESS タスク（自動レビュー対象外）
        task_id_3 = "TASK_003"
        create_test_task(conn, project_id, order_id, task_id_3, "IN_PROGRESS", None)

        # 自動レビュー対象タスクを検索（parallel_launcher.py の検出ロジックを模倣）
        orphaned_tasks = execute_query(
            conn,
            """
            SELECT id, status, reviewed_at, updated_at
            FROM tasks
            WHERE status = 'DONE'
              AND reviewed_at IS NULL
              AND project_id = ?
            ORDER BY updated_at ASC
            """,
            (project_id,)
        ).fetchall()

        # TASK_001 のみが検出されるはず
        assert len(orphaned_tasks) == 1, f"1つのタスクが検出されるべき: {len(orphaned_tasks)}"
        assert orphaned_tasks[0]["id"] == task_id_1, \
            f"TASK_001 が検出されるべき: {orphaned_tasks[0]['id']}"
        print(f"  ✓ 自動レビュー対象タスク検出: {orphaned_tasks[0]['id']}")
        print(f"  ✓ reviewed_at IS NULL 条件で正しくフィルタリングされた")

        print("  PASS: 自動レビュー対象タスクが正しく検出された")

    finally:
        close_connection(conn)


def test_rework_cycle_full_flow():
    """
    テスト3: REWORK→IN_PROGRESS→DONE の完全サイクルを検証

    シナリオ:
    1. タスクを作成し DONE に遷移（初回完了）
    2. PM が REWORK に差し戻し（reviewed_at は保持される）
    3. Worker が IN_PROGRESS に再開（reviewed_at が NULL にリセット）
    4. Worker が DONE に再完了（2回目の DONE、reviewed_at は NULL のまま）
    5. 自動レビューが実行可能な状態であることを確認
    """
    print("\nTest 3: REWORK サイクルの完全フロー検証")

    conn = setup_test_db()
    try:
        project_id = "test_project"
        order_id = "ORDER_001"
        task_id = "TASK_001"

        # プロジェクト・ORDER・タスクを作成
        create_test_project(conn, project_id)
        create_test_order(conn, project_id, order_id)
        create_test_task(conn, project_id, order_id, task_id, "QUEUED", None)

        # 1. QUEUED → IN_PROGRESS → DONE（初回完了）
        print("  [1] 初回完了フロー")
        update_task_status(conn, project_id, task_id, "QUEUED", "IN_PROGRESS")
        update_task_status(conn, project_id, task_id, "IN_PROGRESS", "DONE")

        reviewed_at_1 = get_task_reviewed_at(conn, project_id, task_id)
        assert reviewed_at_1 is None, "初回 DONE 時は reviewed_at は NULL"
        print(f"    ✓ 初回 DONE 完了 (reviewed_at=NULL)")

        # 2. 自動レビュー実行を模倣（reviewed_at を設定）
        print("  [2] 自動レビュー実行（reviewed_at 設定）")
        execute_query(
            conn,
            "UPDATE tasks SET reviewed_at = ? WHERE id = ? AND project_id = ?",
            (datetime.now().isoformat(), task_id, project_id)
        )
        reviewed_at_2 = get_task_reviewed_at(conn, project_id, task_id)
        assert reviewed_at_2 is not None, "レビュー後は reviewed_at が設定される"
        print(f"    ✓ reviewed_at 設定完了: {reviewed_at_2}")

        # 3. PM が REWORK に差し戻し
        print("  [3] PM が REWORK に差し戻し")
        update_task_status(conn, project_id, task_id, "DONE", "REWORK")
        reviewed_at_3 = get_task_reviewed_at(conn, project_id, task_id)
        assert reviewed_at_3 == reviewed_at_2, "REWORK 遷移では reviewed_at は保持される"
        print(f"    ✓ REWORK 遷移完了 (reviewed_at={reviewed_at_3[:19]})")

        # 4. Worker が IN_PROGRESS に再開（reviewed_at が NULL にリセット）
        print("  [4] Worker が IN_PROGRESS に再開")
        update_task_status(conn, project_id, task_id, "REWORK", "IN_PROGRESS")
        reviewed_at_4 = get_task_reviewed_at(conn, project_id, task_id)
        assert reviewed_at_4 is None, "REWORK→IN_PROGRESS で reviewed_at が NULL にリセット"
        print(f"    ✓ reviewed_at リセット完了 (NULL)")

        # 5. Worker が DONE に再完了（2回目の DONE）
        print("  [5] Worker が DONE に再完了（2回目）")
        update_task_status(conn, project_id, task_id, "IN_PROGRESS", "DONE")
        reviewed_at_5 = get_task_reviewed_at(conn, project_id, task_id)
        assert reviewed_at_5 is None, "2回目の DONE でも reviewed_at は NULL のまま"
        print(f"    ✓ 2回目 DONE 完了 (reviewed_at=NULL)")

        # 6. 自動レビュー対象として検出可能であることを確認
        print("  [6] 自動レビュー対象として検出")
        orphaned_tasks = execute_query(
            conn,
            """
            SELECT id FROM tasks
            WHERE status = 'DONE' AND reviewed_at IS NULL AND project_id = ?
            """,
            (project_id,)
        ).fetchall()

        assert len(orphaned_tasks) == 1, "自動レビュー対象として検出されるべき"
        assert orphaned_tasks[0]["id"] == task_id
        print(f"    ✓ 自動レビュー対象として検出成功: {task_id}")

        print("  PASS: REWORK サイクルの完全フローが正常に動作した")

    finally:
        close_connection(conn)


def test_done_to_completed_flow():
    """
    テスト4: DONE→COMPLETED の正常フロー検証
    """
    print("\nTest 4: DONE→COMPLETED の正常フロー")

    conn = setup_test_db()
    try:
        project_id = "test_project"
        order_id = "ORDER_001"
        task_id = "TASK_001"

        # プロジェクト・ORDER・タスクを作成
        create_test_project(conn, project_id)
        create_test_order(conn, project_id, order_id)
        create_test_task(conn, project_id, order_id, task_id, "DONE", None)

        # DONE → COMPLETED（PM承認）
        update_task_status(conn, project_id, task_id, "DONE", "COMPLETED")

        task = fetch_one(
            conn,
            "SELECT status, completed_at FROM tasks WHERE id = ? AND project_id = ?",
            (task_id, project_id)
        )

        assert task["status"] == "COMPLETED", "ステータスが COMPLETED になっているはず"
        assert task["completed_at"] is not None, "completed_at が設定されているはず"
        print(f"  ✓ DONE→COMPLETED 正常完了")
        print(f"  ✓ completed_at: {task['completed_at']}")

        print("  PASS: DONE→COMPLETED フローが正常に動作した")

    finally:
        close_connection(conn)


def test_done_to_rework_flow():
    """
    テスト5: DONE→REWORK の正常フロー検証
    """
    print("\nTest 5: DONE→REWORK の正常フロー")

    conn = setup_test_db()
    try:
        project_id = "test_project"
        order_id = "ORDER_001"
        task_id = "TASK_001"

        # プロジェクト・ORDER・タスクを作成
        create_test_project(conn, project_id)
        create_test_order(conn, project_id, order_id)
        create_test_task(conn, project_id, order_id, task_id, "DONE", None)

        # DONE → REWORK（PM差し戻し）
        update_task_status(conn, project_id, task_id, "DONE", "REWORK")

        task = fetch_one(
            conn,
            "SELECT status, reject_count FROM tasks WHERE id = ? AND project_id = ?",
            (task_id, project_id)
        )

        assert task["status"] == "REWORK", "ステータスが REWORK になっているはず"
        print(f"  ✓ DONE→REWORK 正常完了")
        print(f"  ✓ reject_count: {task['reject_count']}")

        print("  PASS: DONE→REWORK フローが正常に動作した")

    finally:
        close_connection(conn)


def main():
    """全テストを実行"""
    # UTF-8出力設定
    from config import setup_utf8_output
    setup_utf8_output()

    print("=" * 70)
    print("REWORK→IN_PROGRESS→DONE 遷移時の reviewed_at リセット動作確認テスト")
    print("=" * 70)

    try:
        test_rework_in_progress_resets_reviewed_at()
        test_done_task_eligible_for_auto_review()
        test_rework_cycle_full_flow()
        test_done_to_completed_flow()
        test_done_to_rework_flow()

        print("\n" + "=" * 70)
        print("全テスト成功")
        print("=" * 70)
        return 0

    except AssertionError as e:
        print(f"\n[FAIL] テスト失敗: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n[ERROR] 予期しないエラー: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
