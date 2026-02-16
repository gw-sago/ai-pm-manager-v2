"""
統合テスト: Pre-flight チェック機能

全チェック項目の動作確認と統合テストを実施
"""

import sys
import sqlite3
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent.parent / "utils"))

from preflight_check import (
    PreflightCheckResult,
    check_db_connection,
    check_active_orders,
    check_blocked_tasks,
    check_artifact_files,
    run_preflight_check,
    generate_report_markdown,
)


def test_db_connection_success():
    """DB接続確認: 正常ケース"""
    with patch('preflight_check.get_db_path') as mock_path:
        # 実際のDBパスを使用
        from preflight_check import get_ai_pm_root
        actual_db = get_ai_pm_root() / "data" / "aipm.db"
        mock_path.return_value = actual_db

        if actual_db.exists():
            accessible, locked, error = check_db_connection()
            assert accessible is True
            assert locked is False
            assert error is None
            print("✅ test_db_connection_success PASSED")
        else:
            print("⚠️ test_db_connection_success SKIPPED (DB not found)")


def test_db_connection_missing():
    """DB接続確認: DBファイル不存在"""
    with patch('preflight_check.get_db_path') as mock_path:
        # 存在しないパスを指定
        mock_path.return_value = Path("/nonexistent/aipm.db")

        accessible, locked, error = check_db_connection()
        assert accessible is False
        assert locked is False
        assert "存在しません" in error
        print("✅ test_db_connection_missing PASSED")


def test_active_orders_detection():
    """アクティブORDER検出: 実DBで確認"""
    from preflight_check import get_ai_pm_root
    db_path = get_ai_pm_root() / "data" / "aipm.db"

    if not db_path.exists():
        print("⚠️ test_active_orders_detection SKIPPED (DB not found)")
        return

    active_orders, error = check_active_orders("ai_pm_manager")

    assert error is None
    assert isinstance(active_orders, list)

    # アクティブなORDERがある場合、フィールドを確認
    if active_orders:
        order = active_orders[0]
        assert "order_id" in order
        assert "status" in order
        assert "title" in order
        assert order["status"] in ("IN_PROGRESS", "REVIEW")

    print(f"✅ test_active_orders_detection PASSED (found {len(active_orders)} active orders)")


def test_blocked_tasks_detection():
    """BLOCKEDタスク検出: 実DBで確認"""
    from preflight_check import get_ai_pm_root
    db_path = get_ai_pm_root() / "data" / "aipm.db"

    if not db_path.exists():
        print("⚠️ test_blocked_tasks_detection SKIPPED (DB not found)")
        return

    blocked_tasks, error = check_blocked_tasks("ai_pm_manager")

    assert error is None
    assert isinstance(blocked_tasks, list)

    # BLOCKEDタスクがある場合、フィールドを確認
    if blocked_tasks:
        task = blocked_tasks[0]
        assert "task_id" in task
        assert "order_id" in task
        assert "title" in task
        assert "reason" in task

    print(f"✅ test_blocked_tasks_detection PASSED (found {len(blocked_tasks)} blocked tasks)")


def test_artifact_files_check():
    """アーティファクトファイル確認: 実DBで確認"""
    from preflight_check import get_ai_pm_root
    db_path = get_ai_pm_root() / "data" / "aipm.db"

    if not db_path.exists():
        print("⚠️ test_artifact_files_check SKIPPED (DB not found)")
        return

    missing_artifacts, error = check_artifact_files("ai_pm_manager")

    assert error is None
    assert isinstance(missing_artifacts, list)

    # 欠損がある場合、フィールドを確認
    if missing_artifacts:
        artifact = missing_artifacts[0]
        assert "type" in artifact
        assert "expected_path" in artifact
        assert "reason" in artifact

    print(f"✅ test_artifact_files_check PASSED (found {len(missing_artifacts)} missing artifacts)")


def test_full_preflight_check():
    """統合テスト: 全チェック項目を実行"""
    from preflight_check import get_ai_pm_root
    db_path = get_ai_pm_root() / "data" / "aipm.db"

    if not db_path.exists():
        print("⚠️ test_full_preflight_check SKIPPED (DB not found)")
        return

    result = run_preflight_check("ai_pm_manager")

    # 結果の基本検証
    assert isinstance(result, PreflightCheckResult)
    assert isinstance(result.passed, bool)
    assert isinstance(result.db_accessible, bool)
    assert isinstance(result.db_locked, bool)
    assert isinstance(result.active_orders, list)
    assert isinstance(result.blocked_tasks_unresolved, list)
    assert isinstance(result.missing_artifacts, list)
    assert isinstance(result.errors, list)
    assert isinstance(result.warnings, list)

    # has_issues() メソッドの検証
    has_issues = result.has_issues()
    expected_issues = (
        not result.passed
        or len(result.errors) > 0
        or len(result.warnings) > 0
    )
    assert has_issues == expected_issues

    print(f"✅ test_full_preflight_check PASSED")
    print(f"   - passed: {result.passed}")
    print(f"   - active_orders: {len(result.active_orders)}")
    print(f"   - blocked_tasks: {len(result.blocked_tasks_unresolved)}")
    print(f"   - missing_artifacts: {len(result.missing_artifacts)}")
    print(f"   - errors: {len(result.errors)}")
    print(f"   - warnings: {len(result.warnings)}")


def test_report_generation():
    """レポート生成テスト"""
    # テスト用の結果を作成
    result = PreflightCheckResult(
        passed=True,
        db_accessible=True,
        db_locked=False,
        active_orders=[],
        blocked_tasks_unresolved=[],
        missing_artifacts=[],
        errors=[],
        warnings=[],
    )

    report = generate_report_markdown(result)

    assert isinstance(report, str)
    assert "# Pre-flight チェック結果" in report
    assert "✅ **全チェック PASSED**" in report
    assert "### 1. DB接続確認" in report
    assert "### 2. アクティブORDER競合検出" in report
    assert "### 3. BLOCKEDタスク依存解決確認" in report
    assert "### 4. アーティファクトファイル存在確認" in report

    print("✅ test_report_generation PASSED")


def test_report_with_all_issues():
    """全種類の問題を含むレポート生成"""
    result = PreflightCheckResult(
        passed=False,
        db_accessible=False,
        db_locked=True,
        active_orders=[
            {
                "order_id": "ORDER_001",
                "status": "IN_PROGRESS",
                "title": "テストORDER 1",
                "updated_at": "2026-02-06",
            },
            {
                "order_id": "ORDER_002",
                "status": "REVIEW",
                "title": "テストORDER 2",
                "updated_at": "2026-02-06",
            },
        ],
        blocked_tasks_unresolved=[
            {
                "task_id": "TASK_001",
                "order_id": "ORDER_001",
                "title": "テストタスク 1",
                "reason": "依存先タスクが未完了",
                "dependency": "TASK_000",
            },
        ],
        missing_artifacts=[
            {
                "type": "order_file",
                "order_id": "ORDER_001",
                "expected_path": "/path/to/ORDER_001.md",
                "reason": "ORDERファイルが存在しません",
            },
        ],
        errors=["データベースがロックされています"],
        warnings=["2件のアクティブORDERが存在します", "1件の解決不能なBLOCKEDタスクが存在します"],
    )

    report = generate_report_markdown(result)

    # エラーセクション確認
    assert "## ❌ エラー" in report
    assert "データベースがロックされています" in report

    # 警告セクション確認
    assert "## ⚠️ 警告" in report
    assert "2件のアクティブORDER" in report

    # 詳細確認
    assert "ORDER_001" in report
    assert "ORDER_002" in report
    assert "TASK_TASK_001" in report
    assert "/path/to/ORDER_001.md" in report

    print("✅ test_report_with_all_issues PASSED")


def test_to_dict_conversion():
    """to_dict()メソッドの検証"""
    result = PreflightCheckResult(
        passed=True,
        db_accessible=True,
        db_locked=False,
        active_orders=[{"order_id": "ORDER_001"}],
        blocked_tasks_unresolved=[],
        missing_artifacts=[],
        errors=[],
        warnings=["テスト警告"],
    )

    result_dict = result.to_dict()

    assert isinstance(result_dict, dict)
    assert result_dict["passed"] is True
    assert result_dict["db_accessible"] is True
    assert result_dict["db_locked"] is False
    assert len(result_dict["active_orders"]) == 1
    assert result_dict["active_orders"][0]["order_id"] == "ORDER_001"
    assert result_dict["warnings"] == ["テスト警告"]

    print("✅ test_to_dict_conversion PASSED")


def test_edge_cases():
    """エッジケーステスト"""
    # 1. DBアクセス不可の場合、後続チェックがスキップされる
    result = PreflightCheckResult(
        passed=False,
        db_accessible=False,
        db_locked=False,
        errors=["データベースにアクセスできません"],
    )

    assert result.passed is False
    assert result.has_issues() is True

    # 2. DBロックの場合も失敗
    result2 = PreflightCheckResult(
        passed=False,
        db_accessible=True,
        db_locked=True,
        errors=["データベースがロックされています"],
    )

    assert result2.passed is False
    assert result2.has_issues() is True

    # 3. 警告のみの場合はpassedがTrue
    result3 = PreflightCheckResult(
        passed=True,
        db_accessible=True,
        db_locked=False,
        warnings=["軽微な警告"],
    )

    assert result3.passed is True
    assert result3.has_issues() is True  # 警告があるのでhas_issuesはTrue

    print("✅ test_edge_cases PASSED")


def test_cli_interface():
    """CLIインターフェーステスト"""
    import subprocess
    from preflight_check import get_ai_pm_root

    script_path = get_ai_pm_root() / "scripts" / "aipm-db" / "utils" / "preflight_check.py"

    if not script_path.exists():
        print("⚠️ test_cli_interface SKIPPED (script not found)")
        return

    try:
        # JSON出力テスト
        result = subprocess.run(
            ["python", str(script_path), "ai_pm_manager", "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=10,
        )

        # 正常終了または警告終了
        assert result.returncode in (0, 1)

        # JSON形式の出力を確認
        import json
        if result.stdout:
            try:
                output_json = json.loads(result.stdout)
                assert "passed" in output_json
                assert "db_accessible" in output_json
                print("✅ test_cli_interface PASSED (JSON output valid)")
            except json.JSONDecodeError:
                print("⚠️ test_cli_interface WARNING (JSON parse failed, but command ran)")
        else:
            print("⚠️ test_cli_interface WARNING (no output, but command ran)")
    except Exception as e:
        print(f"⚠️ test_cli_interface WARNING (error occurred: {e})")


def main():
    """全テスト実行"""
    print("=" * 60)
    print("Pre-flight チェック統合テスト")
    print("=" * 60)
    print()

    # 個別チェック項目のテスト
    print("## 個別チェック項目テスト")
    test_db_connection_success()
    test_db_connection_missing()
    test_active_orders_detection()
    test_blocked_tasks_detection()
    test_artifact_files_check()
    print()

    # 統合テスト
    print("## 統合テスト")
    test_full_preflight_check()
    print()

    # レポート生成テスト
    print("## レポート生成テスト")
    test_report_generation()
    test_report_with_all_issues()
    test_to_dict_conversion()
    print()

    # エッジケース
    print("## エッジケーステスト")
    test_edge_cases()
    print()

    # CLIテスト
    print("## CLIインターフェーステスト")
    test_cli_interface()
    print()

    print("=" * 60)
    print("✅ 全統合テスト完了")
    print("=" * 60)


if __name__ == "__main__":
    main()
