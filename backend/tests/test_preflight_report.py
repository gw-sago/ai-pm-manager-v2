"""
Test Pre-flight チェックレポート生成機能

チェック結果のMarkdown/JSON形式レポート生成を検証
"""

import sys
from pathlib import Path

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent.parent / "utils"))

from preflight_check import (
    PreflightCheckResult,
    generate_report_markdown,
)


def test_report_all_passed():
    """全チェックPASSED時のレポート生成"""
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

    assert "# Pre-flight チェック結果" in report
    assert "✅ **全チェック PASSED**" in report
    assert "### 1. DB接続確認" in report
    assert "✅ OK" in report
    assert "### 2. アクティブORDER競合検出" in report
    assert "✅ 競合なし" in report
    assert "### 3. BLOCKEDタスク依存解決確認" in report
    assert "✅ 解決不能なBLOCKEDタスクなし" in report
    assert "### 4. アーティファクトファイル存在確認" in report
    assert "✅ 全ファイル存在確認" in report

    print("✅ test_report_all_passed PASSED")


def test_report_with_warnings():
    """警告ありのレポート生成"""
    result = PreflightCheckResult(
        passed=True,
        db_accessible=True,
        db_locked=False,
        active_orders=[
            {
                "order_id": "ORDER_001",
                "status": "IN_PROGRESS",
                "title": "テストORDER",
                "updated_at": "2026-02-06",
            }
        ],
        blocked_tasks_unresolved=[],
        missing_artifacts=[],
        errors=[],
        warnings=["1件のアクティブORDERが存在します: ORDER_001"],
    )

    report = generate_report_markdown(result)

    assert "⚠️ **警告あり（実行可能）**" in report
    assert "## ⚠️ 警告" in report
    assert "1件のアクティブORDERが存在します" in report
    assert "⚠️ 1件のアクティブORDERが存在します" in report
    assert "**ORDER_001**: テストORDER (status: IN_PROGRESS)" in report

    print("✅ test_report_with_warnings PASSED")


def test_report_with_errors():
    """エラーありのレポート生成"""
    result = PreflightCheckResult(
        passed=False,
        db_accessible=False,
        db_locked=False,
        active_orders=[],
        blocked_tasks_unresolved=[],
        missing_artifacts=[],
        errors=["データベースにアクセスできません"],
        warnings=[],
    )

    report = generate_report_markdown(result)

    assert "❌ **FAILED - 実行前に修正が必要です**" in report
    assert "## ❌ エラー" in report
    assert "データベースにアクセスできません" in report
    assert "❌ データベースにアクセスできません" in report

    print("✅ test_report_with_errors PASSED")


def test_report_blocked_tasks():
    """BLOCKEDタスク検出レポート"""
    result = PreflightCheckResult(
        passed=True,
        db_accessible=True,
        db_locked=False,
        active_orders=[],
        blocked_tasks_unresolved=[
            {
                "task_id": "TASK_001",
                "order_id": "ORDER_001",
                "title": "テストタスク",
                "reason": "依存先タスクが未完了 (status: IN_PROGRESS)",
                "dependency": "TASK_000",
            }
        ],
        missing_artifacts=[],
        errors=[],
        warnings=["1件の解決不能なBLOCKEDタスクが存在します"],
    )

    report = generate_report_markdown(result)

    assert "⚠️ 1件の解決不能なBLOCKEDタスクが存在します" in report
    assert "**TASK_TASK_001** (ORDER_001): テストタスク" in report
    assert "理由: 依存先タスクが未完了 (status: IN_PROGRESS)" in report
    assert "依存先: TASK_TASK_000" in report

    print("✅ test_report_blocked_tasks PASSED")


def test_report_missing_artifacts():
    """アーティファクト欠損レポート"""
    result = PreflightCheckResult(
        passed=True,
        db_accessible=True,
        db_locked=False,
        active_orders=[],
        blocked_tasks_unresolved=[],
        missing_artifacts=[
            {
                "type": "order_file",
                "order_id": "ORDER_001",
                "expected_path": "/path/to/ORDER_001.md",
                "reason": "ORDERファイルが存在しません",
            },
            {
                "type": "artifact_dir",
                "task_id": "TASK_001",
                "order_id": "ORDER_001",
                "expected_path": "/path/to/artifacts",
                "reason": "アーティファクトディレクトリが存在しません",
            },
        ],
        errors=[],
        warnings=["2件のファイルが見つかりません"],
    )

    report = generate_report_markdown(result)

    assert "⚠️ 2件のファイルが見つかりません" in report
    assert "**ORDER_001**: ORDERファイルが存在しません" in report
    assert "期待パス: `/path/to/ORDER_001.md`" in report
    assert "**TASK_TASK_001** (ORDER_001): アーティファクトディレクトリが存在しません" in report
    assert "期待パス: `/path/to/artifacts`" in report

    print("✅ test_report_missing_artifacts PASSED")


def test_report_json_conversion():
    """JSON形式への変換"""
    result = PreflightCheckResult(
        passed=True,
        db_accessible=True,
        db_locked=False,
        active_orders=[],
        blocked_tasks_unresolved=[],
        missing_artifacts=[],
        errors=[],
        warnings=["テスト警告"],
    )

    result_dict = result.to_dict()

    assert result_dict["passed"] is True
    assert result_dict["db_accessible"] is True
    assert result_dict["db_locked"] is False
    assert result_dict["active_orders"] == []
    assert result_dict["blocked_tasks_unresolved"] == []
    assert result_dict["missing_artifacts"] == []
    assert result_dict["errors"] == []
    assert result_dict["warnings"] == ["テスト警告"]

    print("✅ test_report_json_conversion PASSED")


def test_has_issues_method():
    """has_issues()メソッド検証"""
    # 問題なし
    result1 = PreflightCheckResult(
        passed=True,
        errors=[],
        warnings=[],
    )
    assert result1.has_issues() is False

    # エラーあり
    result2 = PreflightCheckResult(
        passed=False,
        errors=["エラー"],
        warnings=[],
    )
    assert result2.has_issues() is True

    # 警告あり
    result3 = PreflightCheckResult(
        passed=True,
        errors=[],
        warnings=["警告"],
    )
    assert result3.has_issues() is True

    # passedがFalse
    result4 = PreflightCheckResult(
        passed=False,
        errors=[],
        warnings=[],
    )
    assert result4.has_issues() is True

    print("✅ test_has_issues_method PASSED")


def main():
    """全テスト実行"""
    print("=" * 60)
    print("Pre-flight チェックレポート生成機能テスト")
    print("=" * 60)
    print()

    test_report_all_passed()
    test_report_with_warnings()
    test_report_with_errors()
    test_report_blocked_tasks()
    test_report_missing_artifacts()
    test_report_json_conversion()
    test_has_issues_method()

    print()
    print("=" * 60)
    print("✅ 全テスト PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
