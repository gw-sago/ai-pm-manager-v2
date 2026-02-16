"""
AI PM Framework - レビューキュー管理モジュールのテスト

⚠️ DEPRECATED: このテストファイルは非推奨です。
ORDER_145でreview_queueテーブルが廃止され、reviewed_at方式に移行しました。
このテストは後方互換性のためにのみ残されており、実行する必要はありません。
"""

import sys
import tempfile
from pathlib import Path
from datetime import datetime

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import get_connection, execute_query, init_database, transaction
from config import get_db_config, DBConfig, set_db_config
from review_queue.add import add_to_queue, AddToQueueResult
from review_queue.update import update_review_status, start_review, approve_review, reject_review
from review_queue.list import list_queue, get_queue_summary, QueueItem


def setup_test_db(db_path: Path) -> None:
    """テスト用DBをセットアップ"""
    # スキーマを適用
    config = get_db_config()
    init_database(db_path, config.schema_path)

    # テストデータを投入
    with transaction(db_path=db_path) as conn:
        # プロジェクト
        execute_query(
            conn,
            """
            INSERT INTO projects (id, name, path, status)
            VALUES ('AI_PM_PJ', 'AI PM Project', '/path/to/project', 'IN_PROGRESS')
            """
        )

        # ORDER
        execute_query(
            conn,
            """
            INSERT INTO orders (id, project_id, title, status)
            VALUES ('ORDER_036', 'AI_PM_PJ', 'Test Order', 'IN_PROGRESS')
            """
        )

        # タスク
        tasks = [
            ("TASK_188", "ORDER_036", "タスク1", "IN_PROGRESS", "Worker A"),
            ("TASK_189", "ORDER_036", "タスク2", "IN_PROGRESS", "Worker A"),
            ("TASK_190", "ORDER_036", "タスク3", "REWORK", "Worker B"),  # 差し戻し状態
        ]
        for task in tasks:
            execute_query(
                conn,
                """
                INSERT INTO tasks (id, order_id, title, status, assignee)
                VALUES (?, ?, ?, ?, ?)
                """,
                task
            )


def test_add_to_queue_normal(db_path: Path) -> bool:
    """通常のレビューキュー追加テスト"""
    print("  テスト: 通常のレビューキュー追加...")

    result = add_to_queue(
        project_name="AI_PM_PJ",
        task_id="TASK_188",
        db_path=db_path,
    )

    if not result.success:
        print(f"    [FAIL] {result.error}")
        return False

    if result.priority != "P1":
        print(f"    [FAIL] 優先度が P1 ではない: {result.priority}")
        return False

    # タスクステータスがDONEになっているか確認
    conn = get_connection(db_path)
    try:
        cursor = conn.execute("SELECT status FROM tasks WHERE id = 'TASK_188'")
        row = cursor.fetchone()
        if row["status"] != "DONE":
            print(f"    [FAIL] タスクステータスがDONEではない: {row['status']}")
            return False
    finally:
        conn.close()

    print("    [PASS]")
    return True


def test_add_to_queue_resubmit(db_path: Path) -> bool:
    """差し戻し再提出のテスト（P0優先度）"""
    print("  テスト: 差し戻し再提出（P0優先度）...")

    result = add_to_queue(
        project_name="AI_PM_PJ",
        task_id="TASK_190",  # REWORK状態のタスク
        db_path=db_path,
    )

    if not result.success:
        print(f"    [FAIL] {result.error}")
        return False

    if result.priority != "P0":
        print(f"    [FAIL] 差し戻し再提出の優先度が P0 ではない: {result.priority}")
        return False

    print("    [PASS]")
    return True


def test_add_to_queue_duplicate(db_path: Path) -> bool:
    """重複追加防止のテスト"""
    print("  テスト: 重複追加防止...")

    # 既にキューにあるタスク（TASK_188）を再度追加
    result = add_to_queue(
        project_name="AI_PM_PJ",
        task_id="TASK_188",
        db_path=db_path,
    )

    # 重複はエラーになるべき
    if result.success:
        print("    [FAIL] 重複追加がエラーにならなかった")
        return False

    print("    [PASS]")
    return True


def test_update_review_start(db_path: Path) -> bool:
    """レビュー開始のテスト"""
    print("  テスト: レビュー開始（PENDING → IN_REVIEW）...")

    result = start_review(
        project_name="AI_PM_PJ",
        task_id="TASK_188",
        reviewer="PM",
        db_path=db_path,
    )

    if not result.success:
        print(f"    [FAIL] {result.error}")
        return False

    if result.new_review_status != "IN_REVIEW":
        print(f"    [FAIL] レビューステータスが IN_REVIEW ではない: {result.new_review_status}")
        return False

    print("    [PASS]")
    return True


def test_update_review_approve(db_path: Path) -> bool:
    """レビュー承認のテスト"""
    print("  テスト: レビュー承認（IN_REVIEW → APPROVED）...")

    result = approve_review(
        project_name="AI_PM_PJ",
        task_id="TASK_188",
        reviewer="PM",
        comment="完了条件達成",
        db_path=db_path,
    )

    if not result.success:
        print(f"    [FAIL] {result.error}")
        return False

    if result.new_review_status != "APPROVED":
        print(f"    [FAIL] レビューステータスが APPROVED ではない: {result.new_review_status}")
        return False

    if result.new_task_status != "COMPLETED":
        print(f"    [FAIL] タスクステータスが COMPLETED ではない: {result.new_task_status}")
        return False

    print("    [PASS]")
    return True


def test_update_review_reject(db_path: Path) -> bool:
    """レビュー差し戻しのテスト"""
    print("  テスト: レビュー差し戻し（IN_REVIEW → REJECTED）...")

    # まずTASK_189をキューに追加してレビュー開始
    add_to_queue(
        project_name="AI_PM_PJ",
        task_id="TASK_189",
        db_path=db_path,
    )
    start_review(
        project_name="AI_PM_PJ",
        task_id="TASK_189",
        reviewer="PM",
        db_path=db_path,
    )

    result = reject_review(
        project_name="AI_PM_PJ",
        task_id="TASK_189",
        reviewer="PM",
        comment="テスト不足",
        db_path=db_path,
    )

    if not result.success:
        print(f"    [FAIL] {result.error}")
        return False

    if result.new_review_status != "REJECTED":
        print(f"    [FAIL] レビューステータスが REJECTED ではない: {result.new_review_status}")
        return False

    if result.new_task_status != "REWORK":
        print(f"    [FAIL] タスクステータスが REWORK ではない: {result.new_task_status}")
        return False

    print("    [PASS]")
    return True


def test_list_queue(db_path: Path) -> bool:
    """レビューキュー一覧取得のテスト"""
    print("  テスト: レビューキュー一覧取得...")

    items = list_queue(
        project_name="AI_PM_PJ",
        db_path=db_path,
    )

    # TASK_188は承認済み、TASK_189は差し戻し、TASK_190は再提出
    # PENDING/IN_REVIEW/REJECTED のみが対象
    active_items = [i for i in items if i.review_status in ("PENDING", "IN_REVIEW", "REJECTED")]

    if len(active_items) == 0:
        # 最低1件はあるはず（TASK_190がPENDING、TASK_189がREJECTED）
        print(f"    [FAIL] アクティブなキューアイテムがありません")
        return False

    print(f"    アクティブなキューアイテム数: {len(active_items)}")
    print("    [PASS]")
    return True


def test_list_queue_priority_sort(db_path: Path) -> bool:
    """優先度ソートのテスト"""
    print("  テスト: 優先度ソート（P0 > P1 > P2）...")

    items = list_queue(
        project_name="AI_PM_PJ",
        include_completed=False,
        db_path=db_path,
    )

    if len(items) < 2:
        print(f"    [SKIP] テストに十分なアイテムがありません: {len(items)}")
        return True

    # P0がP1より先に来ているか確認
    priorities = [item.priority for item in items]
    expected_order = sorted(priorities, key=lambda p: {"P0": 0, "P1": 1, "P2": 2}.get(p, 9))

    if priorities == expected_order:
        print(f"    優先度順: {priorities}")
        print("    [PASS]")
        return True
    else:
        print(f"    [FAIL] ソート順が正しくない: {priorities} (期待: {expected_order})")
        return False


def test_queue_summary(db_path: Path) -> bool:
    """キューサマリのテスト"""
    print("  テスト: キューサマリ取得...")

    summary = get_queue_summary("AI_PM_PJ", db_path)

    if "error" in summary:
        print(f"    [FAIL] {summary['error']}")
        return False

    print(f"    PENDING: {summary.get('pending_count', 0)}")
    print(f"    IN_REVIEW: {summary.get('in_review_count', 0)}")
    print(f"    REJECTED: {summary.get('rejected_count', 0)}")
    print(f"    P0: {summary.get('p0_count', 0)}")
    print("    [PASS]")
    return True


def main():
    """テスト実行"""
    print("=" * 60)
    print("レビューキュー管理モジュール テスト")
    print("=" * 60)

    # 一時ディレクトリにテスト用DBを作成
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_queue.db"
        print(f"\nテストDB: {db_path}")

        # セットアップ
        print("\nセットアップ中...")
        try:
            setup_test_db(db_path)
            print("  [OK] テストDBセットアップ完了")
        except Exception as e:
            print(f"  [FAIL] セットアップエラー: {e}")
            import traceback
            traceback.print_exc()
            return 1

        # テスト実行
        print("\nテスト実行中...")
        results = []

        tests = [
            ("add_to_queue (通常)", lambda: test_add_to_queue_normal(db_path)),
            ("add_to_queue (再提出)", lambda: test_add_to_queue_resubmit(db_path)),
            ("add_to_queue (重複防止)", lambda: test_add_to_queue_duplicate(db_path)),
            ("update_review (開始)", lambda: test_update_review_start(db_path)),
            ("update_review (承認)", lambda: test_update_review_approve(db_path)),
            ("update_review (差し戻し)", lambda: test_update_review_reject(db_path)),
            ("list_queue", lambda: test_list_queue(db_path)),
            ("list_queue (優先度ソート)", lambda: test_list_queue_priority_sort(db_path)),
            ("queue_summary", lambda: test_queue_summary(db_path)),
        ]

        for name, test_func in tests:
            try:
                result = test_func()
                results.append((name, result))
            except Exception as e:
                print(f"  テスト {name} で例外発生: {e}")
                import traceback
                traceback.print_exc()
                results.append((name, False))

        # 結果サマリ
        print("\n" + "=" * 60)
        print("テスト結果サマリ")
        print("=" * 60)

        passed = sum(1 for _, r in results if r)
        failed = len(results) - passed

        for name, result in results:
            status = "PASS" if result else "FAIL"
            print(f"  [{status}] {name}")

        print(f"\n合計: {passed}/{len(results)} テスト成功")

        if failed > 0:
            print(f"失敗: {failed}件")
            return 1

        print("\n全テスト成功!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
