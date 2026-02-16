"""
AI PM Framework - 入力検証ユーティリティテスト

utils/validation.py の機能をテスト。
"""

import sys
from pathlib import Path

# 親ディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from aipm_db.utils.validation import (
    validate_project_name,
    validate_order_id,
    validate_task_id,
    validate_backlog_id,
    validate_status,
    validate_priority,
    validate_model,
    parse_task_id,
    ValidationError,
)


def test_validate_project_name():
    """プロジェクト名検証テスト"""
    print("Test: validate_project_name")

    # 有効なプロジェクト名
    valid_names = ["AI_PM_PJ", "MyProject", "project01", "A", "Test_123"]
    for name in valid_names:
        result = validate_project_name(name)
        assert result == name, f"Failed for: {name}"

    # 無効なプロジェクト名
    invalid_names = ["", "123project", "_project", "project-name", "project name"]
    for name in invalid_names:
        try:
            validate_project_name(name)
            assert False, f"Should have raised for: {name}"
        except ValidationError:
            pass

    print("  PASS: Project name validation works correctly")


def test_validate_order_id():
    """ORDER ID検証テスト"""
    print("Test: validate_order_id")

    # 有効なORDER ID
    valid_ids = ["ORDER_001", "ORDER_036", "ORDER_999"]
    for order_id in valid_ids:
        result = validate_order_id(order_id)
        assert result == order_id, f"Failed for: {order_id}"

    # 無効なORDER ID
    invalid_ids = ["", "ORDER_1", "ORDER_12", "ORDER_1234", "ORDER_ABC", "order_001"]
    for order_id in invalid_ids:
        try:
            validate_order_id(order_id)
            assert False, f"Should have raised for: {order_id}"
        except ValidationError:
            pass

    print("  PASS: ORDER ID validation works correctly")


def test_validate_task_id():
    """タスクID検証テスト"""
    print("Test: validate_task_id")

    # 有効なタスクID
    valid_ids = ["TASK_001", "TASK_188", "TASK_075_INT", "TASK_075_INT_02"]
    for task_id in valid_ids:
        result = validate_task_id(task_id)
        assert result == task_id, f"Failed for: {task_id}"

    # 無効なタスクID
    invalid_ids = ["", "TASK_1", "TASK_12", "task_001", "TASK_ABC", "TASK_001_INT_1"]
    for task_id in invalid_ids:
        try:
            validate_task_id(task_id)
            assert False, f"Should have raised for: {task_id}"
        except ValidationError:
            pass

    print("  PASS: Task ID validation works correctly")


def test_validate_backlog_id():
    """BACKLOG ID検証テスト"""
    print("Test: validate_backlog_id")

    # 有効なBACKLOG ID
    valid_ids = ["BACKLOG_001", "BACKLOG_029", "BACKLOG_999"]
    for backlog_id in valid_ids:
        result = validate_backlog_id(backlog_id)
        assert result == backlog_id, f"Failed for: {backlog_id}"

    # 無効なBACKLOG ID
    invalid_ids = ["", "BACKLOG_1", "backlog_001", "BACKLOG_1234"]
    for backlog_id in invalid_ids:
        try:
            validate_backlog_id(backlog_id)
            assert False, f"Should have raised for: {backlog_id}"
        except ValidationError:
            pass

    print("  PASS: BACKLOG ID validation works correctly")


def test_validate_status():
    """ステータス検証テスト"""
    print("Test: validate_status")

    # タスクステータス
    task_statuses = ["QUEUED", "BLOCKED", "IN_PROGRESS", "DONE", "REWORK", "COMPLETED", "INTERRUPTED"]
    for status in task_statuses:
        result = validate_status(status, "task")
        assert result == status

    # ORDERステータス
    order_statuses = ["PLANNING", "IN_PROGRESS", "REVIEW", "COMPLETED", "ON_HOLD", "CANCELLED"]
    for status in order_statuses:
        result = validate_status(status, "order")
        assert result == status

    # 無効なステータス
    try:
        validate_status("INVALID", "task")
        assert False, "Should have raised"
    except ValidationError:
        pass

    # 無効なエンティティ種別
    try:
        validate_status("QUEUED", "invalid_type")
        assert False, "Should have raised"
    except ValidationError:
        pass

    print("  PASS: Status validation works correctly")


def test_validate_priority():
    """優先度検証テスト"""
    print("Test: validate_priority")

    # 有効な優先度
    for priority in ["P0", "P1", "P2"]:
        result = validate_priority(priority)
        assert result == priority

    # 無効な優先度
    for priority in ["P3", "HIGH", "1", ""]:
        try:
            validate_priority(priority)
            assert False, f"Should have raised for: {priority}"
        except ValidationError:
            pass

    print("  PASS: Priority validation works correctly")


def test_validate_model():
    """推奨モデル検証テスト"""
    print("Test: validate_model")

    # 有効なモデル
    for model in ["Haiku", "Sonnet", "Opus"]:
        result = validate_model(model)
        assert result == model

    # 無効なモデル
    for model in ["haiku", "GPT-4", "Claude", ""]:
        try:
            validate_model(model)
            assert False, f"Should have raised for: {model}"
        except ValidationError:
            pass

    print("  PASS: Model validation works correctly")


def test_parse_task_id():
    """タスクIDパーステスト"""
    print("Test: parse_task_id")

    # 通常タスク
    result = parse_task_id("TASK_188")
    assert result["base_number"] == "188"
    assert result["is_interrupt"] is False
    assert result["interrupt_number"] is None

    # 割り込みタスク（基本）
    result = parse_task_id("TASK_075_INT")
    assert result["base_number"] == "075"
    assert result["is_interrupt"] is True
    assert result["interrupt_number"] is None

    # 割り込みタスク（連番付き）
    result = parse_task_id("TASK_075_INT_02")
    assert result["base_number"] == "075"
    assert result["is_interrupt"] is True
    assert result["interrupt_number"] == "02"

    print("  PASS: Task ID parsing works correctly")


def run_all_tests():
    """全テスト実行"""
    print("\n=== Validation Utility Tests ===\n")

    test_validate_project_name()
    test_validate_order_id()
    test_validate_task_id()
    test_validate_backlog_id()
    test_validate_status()
    test_validate_priority()
    test_validate_model()
    test_parse_task_id()

    print("\n=== All Validation tests passed ===\n")


if __name__ == "__main__":
    run_all_tests()
