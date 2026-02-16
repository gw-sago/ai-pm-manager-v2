#!/usr/bin/env python3
"""
AI PM Framework - BACKLOG管理スクリプトのテスト

Tests:
    - add_backlog: BACKLOG追加
    - update_backlog: BACKLOG状態更新
    - list_backlogs: BACKLOG一覧取得
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

from utils.db import get_connection, transaction, execute_query, fetch_one, init_database
from config import get_test_db_config, set_db_config


def setup_test_db():
    """テスト用データベースを初期化"""
    config = get_test_db_config()
    set_db_config(config)

    # スキーマを適用
    init_database(config.db_path, config.schema_path)

    # テスト用プロジェクトを作成
    with transaction(db_path=config.db_path) as conn:
        execute_query(
            conn,
            """
            INSERT OR IGNORE INTO projects (id, name, path, status)
            VALUES (?, ?, ?, ?)
            """,
            ("AI_PM_PJ", "AI PM Framework", "PROJECTS/AI_PM_PJ", "IN_PROGRESS")
        )

        # テスト用ORDERを作成
        execute_query(
            conn,
            """
            INSERT OR IGNORE INTO orders (id, project_id, title, status)
            VALUES (?, ?, ?, ?)
            """,
            ("ORDER_036", "AI_PM_PJ", "Test ORDER", "IN_PROGRESS")
        )

    return config


def teardown_test_db(config):
    """テスト用データベースを削除"""
    if config.db_path.exists():
        config.db_path.unlink()


def test_add_backlog_basic():
    """基本的なBACKLOG追加テスト"""
    config = setup_test_db()
    try:
        from backlog.add import add_backlog

        result = add_backlog(
            project_name="AI_PM_PJ",
            title="テストBACKLOG",
            description="テスト用の説明",
            priority="High",
            render=False,
            db_path=config.db_path,
        )

        assert result.success, f"追加に失敗: {result.error}"
        assert result.backlog_id.startswith("BACKLOG_"), f"IDが不正: {result.backlog_id}"
        assert result.title == "テストBACKLOG"
        assert result.priority == "High"

        print(f"[PASS] test_add_backlog_basic: {result.backlog_id}")

    finally:
        teardown_test_db(config)


def test_add_backlog_auto_id():
    """BACKLOG ID自動採番テスト"""
    config = setup_test_db()
    try:
        from backlog.add import add_backlog

        # 1件目
        result1 = add_backlog(
            project_name="AI_PM_PJ",
            title="BACKLOG 1",
            render=False,
            db_path=config.db_path,
        )
        assert result1.success
        assert result1.backlog_id == "BACKLOG_001"

        # 2件目
        result2 = add_backlog(
            project_name="AI_PM_PJ",
            title="BACKLOG 2",
            render=False,
            db_path=config.db_path,
        )
        assert result2.success
        assert result2.backlog_id == "BACKLOG_002"

        print("[PASS] test_add_backlog_auto_id")

    finally:
        teardown_test_db(config)


def test_add_backlog_with_category():
    """カテゴリ付きBACKLOG追加テスト"""
    config = setup_test_db()
    try:
        from backlog.add import add_backlog

        result = add_backlog(
            project_name="AI_PM_PJ",
            title="バグ修正タスク",
            category="バグ修正",
            priority="High",
            render=False,
            db_path=config.db_path,
        )

        assert result.success
        assert result.category == "バグ修正"

        # DBでカテゴリが説明に含まれているか確認
        with transaction(db_path=config.db_path) as conn:
            row = fetch_one(
                conn,
                "SELECT description FROM backlog_items WHERE id = ?",
                (result.backlog_id,)
            )
            assert "カテゴリ: バグ修正" in row["description"]

        print("[PASS] test_add_backlog_with_category")

    finally:
        teardown_test_db(config)


def test_update_backlog_status():
    """BACKLOG状態更新テスト"""
    config = setup_test_db()
    try:
        from backlog.add import add_backlog
        from backlog.update import update_backlog

        # まずBACKLOGを追加
        add_result = add_backlog(
            project_name="AI_PM_PJ",
            title="更新テスト",
            render=False,
            db_path=config.db_path,
        )
        assert add_result.success

        # IN_PROGRESSに更新（ORDER変換）
        update_result = update_backlog(
            project_name="AI_PM_PJ",
            backlog_id=add_result.backlog_id,
            status="IN_PROGRESS",
            order_id="ORDER_036",
            render=False,
            db_path=config.db_path,
        )

        assert update_result.success, f"更新に失敗: {update_result.error}"
        assert update_result.old_status == "TODO"
        assert update_result.new_status == "IN_PROGRESS"
        assert update_result.related_order_id == "ORDER_036"

        print("[PASS] test_update_backlog_status")

    finally:
        teardown_test_db(config)


def test_update_backlog_to_done():
    """BACKLOG完了（DONE）テスト"""
    config = setup_test_db()
    try:
        from backlog.add import add_backlog
        from backlog.update import update_backlog

        # BACKLOGを追加
        add_result = add_backlog(
            project_name="AI_PM_PJ",
            title="完了テスト",
            render=False,
            db_path=config.db_path,
        )

        # IN_PROGRESSに更新
        update_backlog(
            project_name="AI_PM_PJ",
            backlog_id=add_result.backlog_id,
            status="IN_PROGRESS",
            order_id="ORDER_036",
            render=False,
            db_path=config.db_path,
        )

        # DONEに更新
        done_result = update_backlog(
            project_name="AI_PM_PJ",
            backlog_id=add_result.backlog_id,
            status="DONE",
            render=False,
            db_path=config.db_path,
        )

        assert done_result.success
        assert done_result.new_status == "DONE"

        # completed_atが設定されているか確認
        with transaction(db_path=config.db_path) as conn:
            row = fetch_one(
                conn,
                "SELECT completed_at FROM backlog_items WHERE id = ?",
                (add_result.backlog_id,)
            )
            assert row["completed_at"] is not None

        print("[PASS] test_update_backlog_to_done")

    finally:
        teardown_test_db(config)


def test_update_backlog_invalid_transition():
    """無効な状態遷移テスト（TODO→DONE は不可）"""
    config = setup_test_db()
    try:
        from backlog.add import add_backlog
        from backlog.update import update_backlog

        # BACKLOGを追加
        add_result = add_backlog(
            project_name="AI_PM_PJ",
            title="遷移テスト",
            render=False,
            db_path=config.db_path,
        )

        # TODO → DONE（無効な遷移）
        update_result = update_backlog(
            project_name="AI_PM_PJ",
            backlog_id=add_result.backlog_id,
            status="DONE",
            render=False,
            db_path=config.db_path,
        )

        # 無効な遷移なのでエラーになるべき
        assert not update_result.success
        assert "状態遷移エラー" in update_result.error

        print("[PASS] test_update_backlog_invalid_transition")

    finally:
        teardown_test_db(config)


def test_list_backlogs_basic():
    """BACKLOG一覧取得テスト"""
    config = setup_test_db()
    try:
        from backlog.add import add_backlog
        from backlog.list import list_backlogs

        # 複数のBACKLOGを追加
        add_backlog("AI_PM_PJ", title="BACKLOG A", priority="High", render=False, db_path=config.db_path)
        add_backlog("AI_PM_PJ", title="BACKLOG B", priority="Medium", render=False, db_path=config.db_path)
        add_backlog("AI_PM_PJ", title="BACKLOG C", priority="Low", render=False, db_path=config.db_path)

        # 一覧取得
        result = list_backlogs(
            project_name="AI_PM_PJ",
            db_path=config.db_path,
        )

        assert result.success, f"一覧取得に失敗: {result.error}"
        assert result.total_count == 3
        assert result.filtered_count == 3
        assert len(result.items) == 3

        print("[PASS] test_list_backlogs_basic")

    finally:
        teardown_test_db(config)


def test_list_backlogs_filter_status():
    """ステータスでフィルタテスト"""
    config = setup_test_db()
    try:
        from backlog.add import add_backlog
        from backlog.update import update_backlog
        from backlog.list import list_backlogs

        # BACKLOGを追加
        add_backlog("AI_PM_PJ", title="TODO項目", render=False, db_path=config.db_path)
        res = add_backlog("AI_PM_PJ", title="IN_PROGRESS項目", render=False, db_path=config.db_path)

        # 1件をIN_PROGRESSに
        update_backlog(
            "AI_PM_PJ",
            res.backlog_id,
            status="IN_PROGRESS",
            order_id="ORDER_036",
            render=False,
            db_path=config.db_path,
        )

        # TODOのみ取得
        result = list_backlogs(
            project_name="AI_PM_PJ",
            status="TODO",
            db_path=config.db_path,
        )

        assert result.success
        assert result.filtered_count == 1
        assert result.items[0]["status"] == "TODO"

        print("[PASS] test_list_backlogs_filter_status")

    finally:
        teardown_test_db(config)


def test_list_backlogs_filter_priority():
    """優先度でフィルタテスト"""
    config = setup_test_db()
    try:
        from backlog.add import add_backlog
        from backlog.list import list_backlogs

        # 異なる優先度のBACKLOGを追加
        add_backlog("AI_PM_PJ", title="High項目", priority="High", render=False, db_path=config.db_path)
        add_backlog("AI_PM_PJ", title="Medium項目", priority="Medium", render=False, db_path=config.db_path)
        add_backlog("AI_PM_PJ", title="Low項目", priority="Low", render=False, db_path=config.db_path)

        # Highのみ取得
        result = list_backlogs(
            project_name="AI_PM_PJ",
            priority="High",
            db_path=config.db_path,
        )

        assert result.success
        assert result.filtered_count == 1
        assert result.items[0]["priority"] == "High"

        print("[PASS] test_list_backlogs_filter_priority")

    finally:
        teardown_test_db(config)


def test_list_backlogs_sort_priority():
    """優先度順ソートテスト"""
    config = setup_test_db()
    try:
        from backlog.add import add_backlog
        from backlog.list import list_backlogs

        # 異なる優先度で追加（順序を逆に）
        add_backlog("AI_PM_PJ", title="Low項目", priority="Low", render=False, db_path=config.db_path)
        add_backlog("AI_PM_PJ", title="High項目", priority="High", render=False, db_path=config.db_path)
        add_backlog("AI_PM_PJ", title="Medium項目", priority="Medium", render=False, db_path=config.db_path)

        # 優先度順で取得
        result = list_backlogs(
            project_name="AI_PM_PJ",
            sort_by="priority",
            db_path=config.db_path,
        )

        assert result.success
        assert len(result.items) == 3
        # Highが先頭
        assert result.items[0]["priority"] == "High"
        assert result.items[1]["priority"] == "Medium"
        assert result.items[2]["priority"] == "Low"

        print("[PASS] test_list_backlogs_sort_priority")

    finally:
        teardown_test_db(config)


def test_order_conversion_flow():
    """ORDER変換フロー全体テスト"""
    config = setup_test_db()
    try:
        from backlog.add import add_backlog
        from backlog.update import update_backlog
        from backlog.list import list_backlogs

        # 1. BACKLOG追加
        add_result = add_backlog(
            project_name="AI_PM_PJ",
            title="新機能追加",
            category="機能追加",
            priority="High",
            render=False,
            db_path=config.db_path,
        )
        assert add_result.success
        backlog_id = add_result.backlog_id

        # 初期状態確認
        list_result = list_backlogs("AI_PM_PJ", db_path=config.db_path)
        item = [i for i in list_result.items if i["id"] == backlog_id][0]
        assert item["status"] == "TODO"

        # 2. ORDER変換（TODO → IN_PROGRESS）
        update_result = update_backlog(
            project_name="AI_PM_PJ",
            backlog_id=backlog_id,
            status="IN_PROGRESS",
            order_id="ORDER_036",
            render=False,
            db_path=config.db_path,
        )
        assert update_result.success

        # IN_PROGRESS状態確認
        list_result = list_backlogs("AI_PM_PJ", db_path=config.db_path)
        item = [i for i in list_result.items if i["id"] == backlog_id][0]
        assert item["status"] == "IN_PROGRESS"
        assert item["related_order_id"] == "ORDER_036"

        # 3. ORDER完了（IN_PROGRESS → DONE）
        done_result = update_backlog(
            project_name="AI_PM_PJ",
            backlog_id=backlog_id,
            status="DONE",
            render=False,
            db_path=config.db_path,
        )
        assert done_result.success

        # DONE状態確認
        list_result = list_backlogs("AI_PM_PJ", db_path=config.db_path)
        item = [i for i in list_result.items if i["id"] == backlog_id][0]
        assert item["status"] == "DONE"

        print("[PASS] test_order_conversion_flow")

    finally:
        teardown_test_db(config)


def run_all_tests():
    """全テスト実行"""
    tests = [
        test_add_backlog_basic,
        test_add_backlog_auto_id,
        test_add_backlog_with_category,
        test_update_backlog_status,
        test_update_backlog_to_done,
        test_update_backlog_invalid_transition,
        test_list_backlogs_basic,
        test_list_backlogs_filter_status,
        test_list_backlogs_filter_priority,
        test_list_backlogs_sort_priority,
        test_order_conversion_flow,
    ]

    passed = 0
    failed = 0

    print("=" * 60)
    print("BACKLOG管理スクリプト テスト")
    print("=" * 60)
    print()

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"[ERROR] {test.__name__}: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"結果: {passed} passed, {failed} failed, {len(tests)} total")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
