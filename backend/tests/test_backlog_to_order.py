#!/usr/bin/env python3
"""
AI PM Framework - BACKLOG→ORDER変換スクリプトのテスト

Tests:
    - convert_backlog_to_order: BACKLOG→ORDER変換
    - トランザクションによるロールバック
    - ステータス検証（TODOのみ変換可能）
    - ORDER ID自動採番
    - 優先度変換（BACKLOG → ORDER）
"""

import sys
from pathlib import Path
from datetime import datetime

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import get_connection, transaction, execute_query, fetch_one, fetch_all, init_database
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

    return config


def teardown_test_db(config):
    """テスト用データベースを削除"""
    if config.db_path.exists():
        config.db_path.unlink()


def add_test_backlog(conn, backlog_id: str, title: str, priority: str = "Medium", status: str = "TODO"):
    """テスト用BACKLOGを追加"""
    now = datetime.now().isoformat()
    execute_query(
        conn,
        """
        INSERT INTO backlog_items (id, project_id, title, priority, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (backlog_id, "AI_PM_PJ", title, priority, status, now, now)
    )


def test_convert_basic():
    """基本的なBACKLOG→ORDER変換テスト"""
    config = setup_test_db()
    try:
        from backlog.to_order import convert_backlog_to_order

        # テストBACKLOGを追加
        with transaction(db_path=config.db_path) as conn:
            add_test_backlog(conn, "BACKLOG_001", "テスト機能", "High", "TODO")

        # 変換実行
        result = convert_backlog_to_order(
            project_name="AI_PM_PJ",
            backlog_id="BACKLOG_001",
            render=False,
            db_path=config.db_path,
        )

        assert result.success, f"変換に失敗: {result.error}"
        assert result.backlog_id == "BACKLOG_001"
        assert result.order_id == "ORDER_001"
        assert result.old_status == "TODO"
        assert result.new_status == "IN_PROGRESS"

        # DBで確認
        with transaction(db_path=config.db_path) as conn:
            # BACKLOGステータス確認
            backlog = fetch_one(conn, "SELECT * FROM backlog_items WHERE id = ?", ("BACKLOG_001",))
            assert backlog["status"] == "IN_PROGRESS"
            assert backlog["related_order_id"] == "ORDER_001"

            # ORDER作成確認
            order = fetch_one(conn, "SELECT * FROM orders WHERE id = ?", ("ORDER_001",))
            assert order is not None
            assert order["title"] == "テスト機能"
            assert order["status"] == "PLANNING"

        print("[PASS] test_convert_basic")

    finally:
        teardown_test_db(config)


def test_convert_with_custom_title():
    """ORDER名を指定した変換テスト"""
    config = setup_test_db()
    try:
        from backlog.to_order import convert_backlog_to_order

        with transaction(db_path=config.db_path) as conn:
            add_test_backlog(conn, "BACKLOG_001", "元のタイトル", "Medium", "TODO")

        result = convert_backlog_to_order(
            project_name="AI_PM_PJ",
            backlog_id="BACKLOG_001",
            title="カスタムORDER名",
            render=False,
            db_path=config.db_path,
        )

        assert result.success
        assert result.backlog_title == "元のタイトル"
        assert result.order_title == "カスタムORDER名"

        # DBで確認
        with transaction(db_path=config.db_path) as conn:
            order = fetch_one(conn, "SELECT * FROM orders WHERE id = ?", ("ORDER_001",))
            assert order["title"] == "カスタムORDER名"

        print("[PASS] test_convert_with_custom_title")

    finally:
        teardown_test_db(config)


def test_convert_priority_mapping():
    """優先度変換テスト（BACKLOG → ORDER）"""
    config = setup_test_db()
    try:
        from backlog.to_order import convert_backlog_to_order

        # High → P0
        with transaction(db_path=config.db_path) as conn:
            add_test_backlog(conn, "BACKLOG_001", "High項目", "High", "TODO")

        result = convert_backlog_to_order(
            project_name="AI_PM_PJ",
            backlog_id="BACKLOG_001",
            render=False,
            db_path=config.db_path,
        )
        assert result.success
        assert result.order_priority == "P0"

        # Medium → P1
        with transaction(db_path=config.db_path) as conn:
            add_test_backlog(conn, "BACKLOG_002", "Medium項目", "Medium", "TODO")

        result = convert_backlog_to_order(
            project_name="AI_PM_PJ",
            backlog_id="BACKLOG_002",
            render=False,
            db_path=config.db_path,
        )
        assert result.success
        assert result.order_priority == "P1"

        # Low → P2
        with transaction(db_path=config.db_path) as conn:
            add_test_backlog(conn, "BACKLOG_003", "Low項目", "Low", "TODO")

        result = convert_backlog_to_order(
            project_name="AI_PM_PJ",
            backlog_id="BACKLOG_003",
            render=False,
            db_path=config.db_path,
        )
        assert result.success
        assert result.order_priority == "P2"

        print("[PASS] test_convert_priority_mapping")

    finally:
        teardown_test_db(config)


def test_convert_custom_priority():
    """優先度を明示的に指定した変換テスト"""
    config = setup_test_db()
    try:
        from backlog.to_order import convert_backlog_to_order

        with transaction(db_path=config.db_path) as conn:
            add_test_backlog(conn, "BACKLOG_001", "Low項目", "Low", "TODO")

        # Lowだが P0 で強制指定
        result = convert_backlog_to_order(
            project_name="AI_PM_PJ",
            backlog_id="BACKLOG_001",
            priority="P0",
            render=False,
            db_path=config.db_path,
        )

        assert result.success
        assert result.order_priority == "P0"

        print("[PASS] test_convert_custom_priority")

    finally:
        teardown_test_db(config)


def test_convert_auto_order_id():
    """ORDER ID自動採番テスト"""
    config = setup_test_db()
    try:
        from backlog.to_order import convert_backlog_to_order

        # 複数のBACKLOGを追加
        with transaction(db_path=config.db_path) as conn:
            add_test_backlog(conn, "BACKLOG_001", "項目1", "High", "TODO")
            add_test_backlog(conn, "BACKLOG_002", "項目2", "Medium", "TODO")
            add_test_backlog(conn, "BACKLOG_003", "項目3", "Low", "TODO")

        # 順番に変換
        result1 = convert_backlog_to_order(
            project_name="AI_PM_PJ", backlog_id="BACKLOG_001",
            render=False, db_path=config.db_path
        )
        assert result1.success
        assert result1.order_id == "ORDER_001"

        result2 = convert_backlog_to_order(
            project_name="AI_PM_PJ", backlog_id="BACKLOG_002",
            render=False, db_path=config.db_path
        )
        assert result2.success
        assert result2.order_id == "ORDER_002"

        result3 = convert_backlog_to_order(
            project_name="AI_PM_PJ", backlog_id="BACKLOG_003",
            render=False, db_path=config.db_path
        )
        assert result3.success
        assert result3.order_id == "ORDER_003"

        print("[PASS] test_convert_auto_order_id")

    finally:
        teardown_test_db(config)


def test_convert_custom_order_id():
    """ORDER IDを指定した変換テスト"""
    config = setup_test_db()
    try:
        from backlog.to_order import convert_backlog_to_order

        with transaction(db_path=config.db_path) as conn:
            add_test_backlog(conn, "BACKLOG_001", "テスト項目", "High", "TODO")

        result = convert_backlog_to_order(
            project_name="AI_PM_PJ",
            backlog_id="BACKLOG_001",
            order_id="ORDER_100",
            render=False,
            db_path=config.db_path,
        )

        assert result.success
        assert result.order_id == "ORDER_100"

        print("[PASS] test_convert_custom_order_id")

    finally:
        teardown_test_db(config)


def test_convert_status_validation_in_progress():
    """ステータス検証テスト（IN_PROGRESSは変換不可）"""
    config = setup_test_db()
    try:
        from backlog.to_order import convert_backlog_to_order

        with transaction(db_path=config.db_path) as conn:
            add_test_backlog(conn, "BACKLOG_001", "進行中項目", "High", "IN_PROGRESS")

        result = convert_backlog_to_order(
            project_name="AI_PM_PJ",
            backlog_id="BACKLOG_001",
            render=False,
            db_path=config.db_path,
        )

        assert not result.success
        assert "TODO" in result.error
        assert "IN_PROGRESS" in result.error

        print("[PASS] test_convert_status_validation_in_progress")

    finally:
        teardown_test_db(config)


def test_convert_status_validation_done():
    """ステータス検証テスト（DONEは変換不可）"""
    config = setup_test_db()
    try:
        from backlog.to_order import convert_backlog_to_order

        with transaction(db_path=config.db_path) as conn:
            add_test_backlog(conn, "BACKLOG_001", "完了項目", "High", "DONE")

        result = convert_backlog_to_order(
            project_name="AI_PM_PJ",
            backlog_id="BACKLOG_001",
            render=False,
            db_path=config.db_path,
        )

        assert not result.success
        assert "TODO" in result.error
        assert "DONE" in result.error

        print("[PASS] test_convert_status_validation_done")

    finally:
        teardown_test_db(config)


def test_convert_not_found():
    """存在しないBACKLOGの変換テスト"""
    config = setup_test_db()
    try:
        from backlog.to_order import convert_backlog_to_order

        result = convert_backlog_to_order(
            project_name="AI_PM_PJ",
            backlog_id="BACKLOG_999",
            render=False,
            db_path=config.db_path,
        )

        assert not result.success
        assert "見つかりません" in result.error

        print("[PASS] test_convert_not_found")

    finally:
        teardown_test_db(config)


def test_convert_duplicate_order_id():
    """重複ORDER IDテスト"""
    config = setup_test_db()
    try:
        from backlog.to_order import convert_backlog_to_order

        with transaction(db_path=config.db_path) as conn:
            add_test_backlog(conn, "BACKLOG_001", "項目1", "High", "TODO")
            add_test_backlog(conn, "BACKLOG_002", "項目2", "Medium", "TODO")

        # 1件目を変換
        result1 = convert_backlog_to_order(
            project_name="AI_PM_PJ",
            backlog_id="BACKLOG_001",
            order_id="ORDER_001",
            render=False,
            db_path=config.db_path,
        )
        assert result1.success

        # 同じORDER IDで2件目を変換しようとする
        result2 = convert_backlog_to_order(
            project_name="AI_PM_PJ",
            backlog_id="BACKLOG_002",
            order_id="ORDER_001",
            render=False,
            db_path=config.db_path,
        )
        assert not result2.success
        assert "既に存在" in result2.error

        print("[PASS] test_convert_duplicate_order_id")

    finally:
        teardown_test_db(config)


def test_convert_wrong_project():
    """プロジェクト不一致テスト"""
    config = setup_test_db()
    try:
        from backlog.to_order import convert_backlog_to_order

        # 別プロジェクトを作成
        with transaction(db_path=config.db_path) as conn:
            execute_query(
                conn,
                """
                INSERT INTO projects (id, name, path, status)
                VALUES (?, ?, ?, ?)
                """,
                ("OTHER_PJ", "Other Project", "PROJECTS/OTHER_PJ", "IN_PROGRESS")
            )
            # AI_PM_PJのBACKLOGを追加
            add_test_backlog(conn, "BACKLOG_001", "テスト", "High", "TODO")

        # 別プロジェクトから変換しようとする
        result = convert_backlog_to_order(
            project_name="OTHER_PJ",
            backlog_id="BACKLOG_001",
            render=False,
            db_path=config.db_path,
        )

        assert not result.success
        assert "属していません" in result.error

        print("[PASS] test_convert_wrong_project")

    finally:
        teardown_test_db(config)


def test_convert_transition_history():
    """状態遷移履歴記録テスト"""
    config = setup_test_db()
    try:
        from backlog.to_order import convert_backlog_to_order

        with transaction(db_path=config.db_path) as conn:
            add_test_backlog(conn, "BACKLOG_001", "テスト", "High", "TODO")

        result = convert_backlog_to_order(
            project_name="AI_PM_PJ",
            backlog_id="BACKLOG_001",
            render=False,
            db_path=config.db_path,
        )
        assert result.success

        # 遷移履歴を確認（change_historyテーブル）
        with transaction(db_path=config.db_path) as conn:
            # BACKLOG遷移履歴
            backlog_history = fetch_all(
                conn,
                "SELECT * FROM change_history WHERE entity_type = ? AND entity_id = ? ORDER BY id",
                ("backlog", "BACKLOG_001")
            )
            assert len(backlog_history) >= 1
            # status変更履歴を探す
            status_changes = [h for h in backlog_history if h["field_name"] == "status"]
            assert len(status_changes) >= 1
            assert status_changes[-1]["old_value"] == "TODO"
            assert status_changes[-1]["new_value"] == "IN_PROGRESS"

            # ORDER遷移履歴
            order_history = fetch_all(
                conn,
                "SELECT * FROM change_history WHERE entity_type = ? AND entity_id = ? ORDER BY id",
                ("order", "ORDER_001")
            )
            assert len(order_history) >= 1
            status_changes = [h for h in order_history if h["field_name"] == "status"]
            assert len(status_changes) >= 1
            assert status_changes[-1]["new_value"] == "PLANNING"

        print("[PASS] test_convert_transition_history")

    finally:
        teardown_test_db(config)


def run_all_tests():
    """全テスト実行"""
    tests = [
        test_convert_basic,
        test_convert_with_custom_title,
        test_convert_priority_mapping,
        test_convert_custom_priority,
        test_convert_auto_order_id,
        test_convert_custom_order_id,
        test_convert_status_validation_in_progress,
        test_convert_status_validation_done,
        test_convert_not_found,
        test_convert_duplicate_order_id,
        test_convert_wrong_project,
        test_convert_transition_history,
    ]

    passed = 0
    failed = 0

    print("=" * 60)
    print("BACKLOG→ORDER変換スクリプト テスト")
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
            import traceback
            traceback.print_exc()
            failed += 1

    print()
    print("=" * 60)
    print(f"結果: {passed} passed, {failed} failed, {len(tests)} total")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
