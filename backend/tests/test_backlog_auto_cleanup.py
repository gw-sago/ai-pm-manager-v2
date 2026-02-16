#!/usr/bin/env python3
"""
AI PM Framework - BACKLOG自動整理機能の統合テスト

ORDER_086: TASK_908
バックログ自動整理機能（自動DONE更新 + 手動一括整理）の統合テスト

Test Coverage:
    1. ORDER完了時の自動BACKLOG DONE更新
    2. 手動一括整理ボタンによる整理実行
    3. 孤立バックログの検出
    4. エラーケースのハンドリング

Usage:
    pytest tests/test_backlog_auto_cleanup.py -v
    python -m pytest tests/test_backlog_auto_cleanup.py::test_auto_done_on_order_complete -v
"""

import pytest
import tempfile
import sqlite3
from pathlib import Path
from datetime import datetime

# テスト対象モジュール
import sys
_test_dir = Path(__file__).resolve().parent
_package_root = _test_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from backlog.auto_done import auto_update_backlog_on_order_complete
from backlog.bulk_cleanup import cleanup_all_backlogs
from order.update import complete_order
from utils.db import get_connection, execute_query


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def test_db():
    """テスト用のインメモリデータベースを作成"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = Path(f.name)

    # スキーマ作成
    # 正しいパスを設定（scriptsディレクトリから2つ上がってPROJECTSへ）
    workspace_root = _package_root.parent.parent
    schema_path = workspace_root / "data" / "schema_v2.sql"

    conn = sqlite3.connect(str(db_path))
    with open(schema_path, 'r', encoding='utf-8') as f:
        conn.executescript(f.read())
    conn.close()

    # テストデータ投入
    _setup_test_data(db_path)

    yield db_path

    # クリーンアップ
    db_path.unlink()


def _setup_test_data(db_path: Path):
    """テストデータを投入"""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    # プロジェクト
    cursor.execute(
        "INSERT INTO projects (id, name, path, status) VALUES (?, ?, ?, ?)",
        ("test_project", "Test Project", "/test/path", "IN_PROGRESS")
    )

    # ORDER群
    orders = [
        ("ORDER_001", "test_project", "完了済みORDER", "P0", "COMPLETED", now, now),
        ("ORDER_002", "test_project", "進行中ORDER", "P0", "IN_PROGRESS", now, None),
        ("ORDER_003", "test_project", "レビュー中ORDER", "P1", "REVIEW", now, None),
    ]
    for order in orders:
        cursor.execute(
            """
            INSERT INTO orders (id, project_id, title, priority, status, started_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            order
        )

    # BACKLOG群
    backlogs = [
        # 正常ケース: COMPLETED済みORDERに紐づくIN_PROGRESS
        ("BACKLOG_001", "test_project", "完了ORDER紐付きバックログ", "High", "IN_PROGRESS", "ORDER_001"),
        # 孤立ケース1: ORDERなし
        ("BACKLOG_002", "test_project", "ORDER未割り当てバックログ", "Medium", "IN_PROGRESS", None),
        # 孤立ケース2: 非COMPLETEDのORDER
        ("BACKLOG_003", "test_project", "進行中ORDER紐付きバックログ", "High", "IN_PROGRESS", "ORDER_002"),
        # 既にDONE
        ("BACKLOG_004", "test_project", "既に完了バックログ", "Low", "DONE", "ORDER_001"),
        # TODO状態
        ("BACKLOG_005", "test_project", "TODO状態バックログ", "Medium", "TODO", None),
    ]
    for backlog in backlogs:
        cursor.execute(
            """
            INSERT INTO backlog_items (id, project_id, title, priority, status, related_order_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            backlog
        )

    conn.commit()
    conn.close()


# =============================================================================
# Tests: auto_done.py (ORDER完了時の自動DONE更新)
# =============================================================================

def test_auto_done_on_order_complete(test_db):
    """ORDER完了時に紐付きBACKLOGが自動的にDONEになることを確認"""
    # 新規ORDERとBACKLOGを作成
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO orders (id, project_id, title, priority, status, started_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("ORDER_100", "test_project", "新規ORDER", "P0", "IN_PROGRESS", datetime.now().isoformat())
    )
    cursor.execute(
        """
        INSERT INTO backlog_items (id, project_id, title, priority, status, related_order_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("BACKLOG_100", "test_project", "新規バックログ", "High", "IN_PROGRESS", "ORDER_100")
    )
    conn.commit()
    conn.close()

    # ORDER完了
    result = auto_update_backlog_on_order_complete(
        "test_project",
        "ORDER_100",
        "テスト: ORDER完了",
        db_path=test_db
    )

    # 検証
    assert result["success"] is True
    assert result["backlog_id"] == "BACKLOG_100"
    assert result["old_status"] == "IN_PROGRESS"
    assert result["new_status"] == "DONE"

    # DB確認
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()
    cursor.execute(
        "SELECT status, completed_at FROM backlog_items WHERE id = ?",
        ("BACKLOG_100",)
    )
    row = cursor.fetchone()
    conn.close()

    assert row[0] == "DONE"
    assert row[1] is not None  # completed_atが設定されている


def test_auto_done_already_done(test_db):
    """既にDONEのBACKLOGは更新されないことを確認"""
    # BACKLOG_004は既にDONEなので、これを使ってテスト
    # まずBACKLOG_004のrelated_order_idを確認
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()
    cursor.execute("SELECT status, related_order_id FROM backlog_items WHERE id = ?", ("BACKLOG_004",))
    row = cursor.fetchone()
    conn.close()

    assert row[0] == "DONE"  # 初期状態でDONE

    result = auto_update_backlog_on_order_complete(
        "test_project",
        "ORDER_001",
        "テスト: 既にDONE",
        db_path=test_db
    )

    # BACKLOG_001がIN_PROGRESSなので、それが更新される
    # BACKLOG_004は既にDONEなので無視される
    assert result["success"] is True
    assert result["backlog_id"] == "BACKLOG_001"  # BACKLOG_001が更新される
    assert result["message"].find("DONE") != -1


def test_auto_done_no_backlog(test_db):
    """ORDERに紐づくBACKLOGがない場合（手動ORDER）"""
    # 紐付きなしORDER
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO orders (id, project_id, title, priority, status, started_at, completed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("ORDER_200", "test_project", "手動ORDER", "P1", "COMPLETED", datetime.now().isoformat(), datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

    result = auto_update_backlog_on_order_complete(
        "test_project",
        "ORDER_200",
        db_path=test_db
    )

    assert result["success"] is True
    assert result["backlog_id"] is None
    assert result["message"].find("紐付くBACKLOGはありません") != -1


def test_auto_done_invalid_project(test_db):
    """存在しないプロジェクトを指定した場合"""
    result = auto_update_backlog_on_order_complete(
        "invalid_project",
        "ORDER_001",
        db_path=test_db
    )

    assert result["success"] is False
    assert "プロジェクトが見つかりません" in result["error"]


def test_auto_done_invalid_order(test_db):
    """存在しないORDERを指定した場合"""
    result = auto_update_backlog_on_order_complete(
        "test_project",
        "ORDER_999",
        db_path=test_db
    )

    assert result["success"] is False
    assert "ORDERが見つかりません" in result["error"]


# =============================================================================
# Tests: bulk_cleanup.py (手動一括整理)
# =============================================================================

def test_bulk_cleanup_dry_run(test_db):
    """一括整理（プレビューモード）"""
    result = cleanup_all_backlogs(
        project_id="test_project",
        dry_run=True,
        db_path=test_db
    )

    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["updated_count"] == 1  # BACKLOG_001のみ
    assert result["orphaned_count"] == 2  # BACKLOG_002, BACKLOG_003

    # プレビューモードではDBは更新されない
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()
    cursor.execute(
        "SELECT status FROM backlog_items WHERE id = ?",
        ("BACKLOG_001",)
    )
    row = cursor.fetchone()
    conn.close()

    assert row[0] == "IN_PROGRESS"  # まだ変更されていない


def test_bulk_cleanup_execute(test_db):
    """一括整理（実行モード）"""
    result = cleanup_all_backlogs(
        project_id="test_project",
        dry_run=False,
        db_path=test_db
    )

    assert result["success"] is True
    assert result["dry_run"] is False
    assert result["updated_count"] == 1  # BACKLOG_001
    assert result["orphaned_count"] == 2  # BACKLOG_002, BACKLOG_003

    # DBが更新されている
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()
    cursor.execute(
        "SELECT status, completed_at FROM backlog_items WHERE id = ?",
        ("BACKLOG_001",)
    )
    row = cursor.fetchone()
    conn.close()

    assert row[0] == "DONE"
    assert row[1] is not None


def test_bulk_cleanup_all_projects(test_db):
    """全プロジェクトを対象に一括整理"""
    # 別プロジェクトを追加
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO projects (id, name, path, status) VALUES (?, ?, ?, ?)",
        ("test_project_2", "Test Project 2", "/test/path2", "IN_PROGRESS")
    )
    cursor.execute(
        """
        INSERT INTO orders (id, project_id, title, priority, status, started_at, completed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("ORDER_300", "test_project_2", "別プロジェクトORDER", "P0", "COMPLETED", datetime.now().isoformat(), datetime.now().isoformat())
    )
    cursor.execute(
        """
        INSERT INTO backlog_items (id, project_id, title, priority, status, related_order_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("BACKLOG_300", "test_project_2", "別プロジェクトバックログ", "High", "IN_PROGRESS", "ORDER_300")
    )
    conn.commit()
    conn.close()

    # 全プロジェクト整理
    result = cleanup_all_backlogs(
        project_id=None,
        dry_run=False,
        db_path=test_db
    )

    assert result["success"] is True
    assert result["updated_count"] == 2  # BACKLOG_001, BACKLOG_300


def test_bulk_cleanup_orphaned_detection(test_db):
    """孤立バックログの検出"""
    result = cleanup_all_backlogs(
        project_id="test_project",
        dry_run=True,
        db_path=test_db
    )

    assert result["success"] is True
    assert result["orphaned_count"] == 2

    # 孤立理由の確認
    orphaned_ids = [item["id"] for item in result["orphaned_backlogs"]]
    assert "BACKLOG_002" in orphaned_ids  # ORDERなし
    assert "BACKLOG_003" in orphaned_ids  # 非COMPLETEDのORDER

    # 詳細確認
    backlog_002 = next(item for item in result["orphaned_backlogs"] if item["id"] == "BACKLOG_002")
    assert backlog_002["reason"] == "ORDERが未割り当て"

    backlog_003 = next(item for item in result["orphaned_backlogs"] if item["id"] == "BACKLOG_003")
    assert "非COMPLETED" in backlog_003["reason"]


def test_bulk_cleanup_invalid_project(test_db):
    """存在しないプロジェクトを指定した場合"""
    result = cleanup_all_backlogs(
        project_id="invalid_project",
        dry_run=False,
        db_path=test_db
    )

    assert result["success"] is False
    assert "プロジェクトが見つかりません" in result["error"]


# =============================================================================
# Tests: 統合シナリオ
# =============================================================================

def test_integration_order_complete_with_cleanup(test_db):
    """ORDERを段階的に完了させ、自動DONE更新を確認する統合テスト"""
    # 新規ORDERとBACKLOGを作成
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO orders (id, project_id, title, priority, status)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("ORDER_400", "test_project", "統合テストORDER", "P0", "PLANNING")
    )
    cursor.execute(
        """
        INSERT INTO backlog_items (id, project_id, title, priority, status, related_order_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("BACKLOG_400", "test_project", "統合テストバックログ", "High", "TODO", "ORDER_400")
    )
    conn.commit()

    # BACKLOGをIN_PROGRESSに更新
    cursor.execute(
        "UPDATE backlog_items SET status = 'IN_PROGRESS' WHERE id = ?",
        ("BACKLOG_400",)
    )
    conn.commit()
    conn.close()

    # 一括整理（プレビュー）- まだ更新されないはず
    result_before = cleanup_all_backlogs(
        project_id="test_project",
        dry_run=True,
        db_path=test_db
    )
    assert result_before["updated_count"] == 1  # BACKLOG_001のみ

    # ORDER完了（complete_order関数は自動的にバックログDONE更新を行う）
    # 注: complete_order()内で _complete_related_backlog() が呼ばれる
    # ※ このテストではorder/update.pyの完全な統合は省略し、auto_done単体をテスト
    result_auto = auto_update_backlog_on_order_complete(
        "test_project",
        "ORDER_400",
        db_path=test_db
    )

    # 検証: BACKLOGは自動的にDONEになる
    assert result_auto["success"] is True
    assert result_auto["backlog_id"] == "BACKLOG_400"
    assert result_auto["new_status"] == "DONE"

    # 一括整理（実行）- 既にDONEなので更新対象外
    result_after = cleanup_all_backlogs(
        project_id="test_project",
        dry_run=False,
        db_path=test_db
    )
    # BACKLOG_400は既にDONEなので、更新対象はBACKLOG_001のみ
    assert result_after["updated_count"] == 1


# =============================================================================
# 実行
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
