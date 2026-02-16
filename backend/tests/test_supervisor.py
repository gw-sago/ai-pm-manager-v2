#!/usr/bin/env python3
"""
AI PM Framework - Supervisor機能の統合テスト

Tests:
    - Supervisor CRUD操作
    - プロジェクト割当/解除
    - 横断バックログ CRUD
    - 振り分け分析・実行
    - ダッシュボード
"""

import json
import sys
import tempfile
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

    # Supervisorテーブルがない場合はマイグレーション実行
    with transaction(db_path=config.db_path) as conn:
        # supervisorsテーブル存在確認
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='supervisors'"
        ).fetchone()

        if not result:
            # マイグレーション相当の処理
            conn.execute("""
                CREATE TABLE IF NOT EXISTS supervisors (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    status TEXT DEFAULT 'ACTIVE',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    CHECK (status IN ('ACTIVE', 'INACTIVE'))
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS cross_project_backlog (
                    id TEXT PRIMARY KEY,
                    supervisor_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    priority TEXT DEFAULT 'Medium',
                    status TEXT DEFAULT 'PENDING',
                    assigned_project_id TEXT,
                    assigned_backlog_id TEXT,
                    analysis_result TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (supervisor_id) REFERENCES supervisors(id) ON DELETE CASCADE,
                    CHECK (priority IN ('High', 'Medium', 'Low')),
                    CHECK (status IN ('PENDING', 'ANALYZING', 'ASSIGNED', 'DONE', 'CANCELED'))
                )
            """)

            # projects.supervisor_id追加（既存テーブルの場合）
            try:
                conn.execute("ALTER TABLE projects ADD COLUMN supervisor_id TEXT")
            except Exception:
                pass  # 既に存在する場合は無視

        # テスト用プロジェクトを作成
        execute_query(
            conn,
            """
            INSERT OR IGNORE INTO projects (id, name, path, status)
            VALUES (?, ?, ?, ?)
            """,
            ("TEST_PJ_1", "Test Project 1", "PROJECTS/TEST_PJ_1", "IN_PROGRESS")
        )

        execute_query(
            conn,
            """
            INSERT OR IGNORE INTO projects (id, name, path, status)
            VALUES (?, ?, ?, ?)
            """,
            ("TEST_PJ_2", "Test Project 2", "PROJECTS/TEST_PJ_2", "IN_PROGRESS")
        )

    return config


def teardown_test_db(config):
    """テスト用データベースを削除"""
    if config.db_path.exists():
        config.db_path.unlink()


# =============================================================================
# Supervisor CRUD テスト
# =============================================================================

def test_supervisor_create():
    """Supervisor作成テスト"""
    config = setup_test_db()
    try:
        from supervisor.create import create_supervisor

        result = create_supervisor(
            supervisor_id="SUPERVISOR_001",
            name="テスト統括",
            description="テスト用統括"
        )

        assert result['id'] == "SUPERVISOR_001"
        assert result['name'] == "テスト統括"
        assert result['status'] == "ACTIVE"
        print("[PASS] test_supervisor_create")

    except Exception as e:
        print(f"[FAIL] test_supervisor_create: FAILED - {e}")
        raise
    finally:
        teardown_test_db(config)


def test_supervisor_create_auto_id():
    """Supervisor自動採番テスト"""
    config = setup_test_db()
    try:
        from supervisor.create import create_supervisor

        # 最初のSupervisor
        result1 = create_supervisor(name="統括1")
        assert result1['id'] == "SUPERVISOR_001"

        # 2つ目のSupervisor
        result2 = create_supervisor(name="統括2")
        assert result2['id'] == "SUPERVISOR_002"

        print("[PASS] test_supervisor_create_auto_id: PASSED")

    except Exception as e:
        print(f"[FAIL] test_supervisor_create_auto_id: FAILED - {e}")
        raise
    finally:
        teardown_test_db(config)


def test_supervisor_list():
    """Supervisor一覧テスト"""
    config = setup_test_db()
    try:
        from supervisor.create import create_supervisor
        from supervisor.list import list_supervisors

        # Supervisor作成
        create_supervisor(name="統括1")
        create_supervisor(name="統括2")

        # 一覧取得
        result = list_supervisors()
        assert len(result) == 2
        assert result[0]['name'] == "統括1"

        print("[PASS] test_supervisor_list: PASSED")

    except Exception as e:
        print(f"[FAIL] test_supervisor_list: FAILED - {e}")
        raise
    finally:
        teardown_test_db(config)


def test_supervisor_update():
    """Supervisor更新テスト"""
    config = setup_test_db()
    try:
        from supervisor.create import create_supervisor
        from supervisor.update import update_supervisor

        # 作成
        create_supervisor(supervisor_id="SUPERVISOR_001", name="旧名前")

        # 更新
        result = update_supervisor("SUPERVISOR_001", name="新名前", status="INACTIVE")

        assert result['name'] == "新名前"
        assert result['status'] == "INACTIVE"
        print("[PASS] test_supervisor_update: PASSED")

    except Exception as e:
        print(f"[FAIL] test_supervisor_update: FAILED - {e}")
        raise
    finally:
        teardown_test_db(config)


def test_supervisor_delete():
    """Supervisor削除テスト"""
    config = setup_test_db()
    try:
        from supervisor.create import create_supervisor
        from supervisor.delete import delete_supervisor
        from supervisor.list import list_supervisors

        # 作成
        create_supervisor(supervisor_id="SUPERVISOR_001", name="削除対象")

        # 削除
        result = delete_supervisor("SUPERVISOR_001")
        assert result['success'] is True

        # 一覧確認（削除されていること）
        supervisors = list_supervisors()
        assert len(supervisors) == 0

        print("[PASS] test_supervisor_delete: PASSED")

    except Exception as e:
        print(f"[FAIL] test_supervisor_delete: FAILED - {e}")
        raise
    finally:
        teardown_test_db(config)


# =============================================================================
# プロジェクト割当テスト
# =============================================================================

def test_project_assign():
    """プロジェクト割当テスト"""
    config = setup_test_db()
    try:
        from supervisor.create import create_supervisor
        from supervisor.assign import assign_project_to_supervisor

        # Supervisor作成
        create_supervisor(supervisor_id="SUPERVISOR_001", name="テスト統括")

        # 割当
        result = assign_project_to_supervisor("TEST_PJ_1", "SUPERVISOR_001")

        assert result['success'] is True
        assert result['supervisor_id'] == "SUPERVISOR_001"
        print("[PASS] test_project_assign: PASSED")

    except Exception as e:
        print(f"[FAIL] test_project_assign: FAILED - {e}")
        raise
    finally:
        teardown_test_db(config)


def test_project_unassign():
    """プロジェクト割当解除テスト"""
    config = setup_test_db()
    try:
        from supervisor.create import create_supervisor
        from supervisor.assign import assign_project_to_supervisor
        from supervisor.unassign import unassign_project_from_supervisor

        # Supervisor作成と割当
        create_supervisor(supervisor_id="SUPERVISOR_001", name="テスト統括")
        assign_project_to_supervisor("TEST_PJ_1", "SUPERVISOR_001")

        # 解除
        result = unassign_project_from_supervisor("TEST_PJ_1")

        assert result['success'] is True
        assert result['previous_supervisor_id'] == "SUPERVISOR_001"
        print("[PASS] test_project_unassign: PASSED")

    except Exception as e:
        print(f"[FAIL] test_project_unassign: FAILED - {e}")
        raise
    finally:
        teardown_test_db(config)


# =============================================================================
# 横断バックログテスト
# =============================================================================

def test_xbacklog_add():
    """横断バックログ追加テスト"""
    config = setup_test_db()
    try:
        from supervisor.create import create_supervisor
        from xbacklog.add import add_xbacklog

        # Supervisor作成
        create_supervisor(supervisor_id="SUPERVISOR_001", name="テスト統括")

        # 横断バックログ追加
        result = add_xbacklog(
            "SUPERVISOR_001",
            title="テスト横断バックログ",
            priority="High"
        )

        assert result['id'] == "XBACKLOG_001"
        assert result['supervisor_id'] == "SUPERVISOR_001"
        assert result['status'] == "PENDING"
        print("[PASS] test_xbacklog_add: PASSED")

    except Exception as e:
        print(f"[FAIL] test_xbacklog_add: FAILED - {e}")
        raise
    finally:
        teardown_test_db(config)


def test_xbacklog_list():
    """横断バックログ一覧テスト"""
    config = setup_test_db()
    try:
        from supervisor.create import create_supervisor
        from xbacklog.add import add_xbacklog
        from xbacklog.list import list_xbacklog

        # 準備
        create_supervisor(supervisor_id="SUPERVISOR_001", name="テスト統括")
        add_xbacklog("SUPERVISOR_001", title="バックログ1")
        add_xbacklog("SUPERVISOR_001", title="バックログ2", priority="High")

        # 一覧取得
        result = list_xbacklog("SUPERVISOR_001")
        assert len(result) == 2

        # 優先度フィルタ
        result_high = list_xbacklog("SUPERVISOR_001", priority="High")
        assert len(result_high) == 1
        assert result_high[0]['title'] == "バックログ2"

        print("[PASS] test_xbacklog_list: PASSED")

    except Exception as e:
        print(f"[FAIL] test_xbacklog_list: FAILED - {e}")
        raise
    finally:
        teardown_test_db(config)


def test_xbacklog_update():
    """横断バックログ更新テスト"""
    config = setup_test_db()
    try:
        from supervisor.create import create_supervisor
        from xbacklog.add import add_xbacklog
        from xbacklog.update import update_xbacklog

        # 準備
        create_supervisor(supervisor_id="SUPERVISOR_001", name="テスト統括")
        add_xbacklog("SUPERVISOR_001", title="元のタイトル")

        # 更新
        result = update_xbacklog("XBACKLOG_001", title="新しいタイトル", status="ANALYZING")

        assert result['title'] == "新しいタイトル"
        assert result['status'] == "ANALYZING"
        print("[PASS] test_xbacklog_update: PASSED")

    except Exception as e:
        print(f"[FAIL] test_xbacklog_update: FAILED - {e}")
        raise
    finally:
        teardown_test_db(config)


# =============================================================================
# 振り分けテスト
# =============================================================================

def test_dispatch_manual():
    """手動振り分けテスト"""
    config = setup_test_db()
    try:
        from supervisor.create import create_supervisor
        from supervisor.assign import assign_project_to_supervisor
        from xbacklog.add import add_xbacklog
        from xbacklog.dispatch import dispatch_xbacklog

        # 準備
        create_supervisor(supervisor_id="SUPERVISOR_001", name="テスト統括")
        assign_project_to_supervisor("TEST_PJ_1", "SUPERVISOR_001")
        add_xbacklog("SUPERVISOR_001", title="振り分け対象")

        # 手動振り分け
        result = dispatch_xbacklog("XBACKLOG_001", project_id="TEST_PJ_1")

        assert result['success'] is True
        assert result['assigned_project_id'] == "TEST_PJ_1"
        assert result['assigned_backlog_id'].startswith("BACKLOG_")
        print("[PASS] test_dispatch_manual: PASSED")

    except Exception as e:
        print(f"[FAIL] test_dispatch_manual: FAILED - {e}")
        raise
    finally:
        teardown_test_db(config)


# =============================================================================
# ダッシュボードテスト
# =============================================================================

def test_dashboard():
    """ダッシュボードテスト"""
    config = setup_test_db()
    try:
        from supervisor.create import create_supervisor
        from supervisor.assign import assign_project_to_supervisor
        from supervisor.dashboard import get_supervisor_dashboard

        # 準備
        create_supervisor(supervisor_id="SUPERVISOR_001", name="テスト統括")
        assign_project_to_supervisor("TEST_PJ_1", "SUPERVISOR_001")
        assign_project_to_supervisor("TEST_PJ_2", "SUPERVISOR_001")

        # ダッシュボード取得
        result = get_supervisor_dashboard("SUPERVISOR_001")

        assert result['supervisor_id'] == "SUPERVISOR_001"
        assert result['project_count'] == 2
        assert 'summary' in result
        print("[PASS] test_dashboard: PASSED")

    except Exception as e:
        print(f"[FAIL] test_dashboard: FAILED - {e}")
        raise
    finally:
        teardown_test_db(config)


# =============================================================================
# メイン
# =============================================================================

def run_all_tests():
    """全テストを実行"""
    print("\n" + "=" * 60)
    print("  Supervisor機能 統合テスト")
    print("=" * 60 + "\n")

    tests = [
        # Supervisor CRUD
        test_supervisor_create,
        test_supervisor_create_auto_id,
        test_supervisor_list,
        test_supervisor_update,
        test_supervisor_delete,

        # プロジェクト割当
        test_project_assign,
        test_project_unassign,

        # 横断バックログ
        test_xbacklog_add,
        test_xbacklog_list,
        test_xbacklog_update,

        # 振り分け
        test_dispatch_manual,

        # ダッシュボード
        test_dashboard,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  Error: {e}")

    print("\n" + "-" * 60)
    print(f"  Results: {passed} passed, {failed} failed")
    print("-" * 60 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
