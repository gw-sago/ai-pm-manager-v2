#!/usr/bin/env python3
"""
AI PM Framework - ORDER再実行スクリプト

PLANNING_FAILED または失敗したORDERをPLANNINGステータスに戻し、
再実行可能な状態にリセットする。

Usage:
    python backend/order/retry_order.py PROJECT_NAME ORDER_ID [options]

Options:
    --timeout       タイムアウト秒数（デフォルト: 600）
    --model         AIモデル（haiku/sonnet/opus、デフォルト: sonnet）
    --verbose       詳細ログ出力
    --json          JSON形式で出力

Example:
    python backend/order/retry_order.py ai_pm_manager_v2 ORDER_075 --json
    python backend/order/retry_order.py ai_pm_manager_v2 ORDER_075 --model haiku --json
    python backend/order/retry_order.py ai_pm_manager_v2 ORDER_075 --timeout 300 --json
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional


# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import (
    get_connection, transaction, execute_query, fetch_one,
    row_to_dict, DatabaseError
)
from utils.validation import (
    validate_project_name, validate_order_id,
    order_exists, ValidationError
)


# 再実行可能なORDERステータス
# PLANNING_FAILEDはvalidation.pyの定義には含まれるが、DBスキーマでは
# 実際には保存されないため、ON_HOLD/CANCELLEDをリセット対象とする
RETRYABLE_STATUSES = [
    "PLANNING_FAILED",  # 将来的なDB拡張に備えて含める
    "PLANNING",
    "ON_HOLD",
    "CANCELLED",
    "IN_PROGRESS",      # スタック状態からのリセット
]


def retry_order(
    project_id: str,
    order_id: str,
    *,
    timeout: int = 600,
    model: str = "sonnet",
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    ORDERをPLANNINGステータスにリセットして再実行可能な状態にする

    PLANNING_FAILED または他の失敗/停止状態のORDERをPLANNINGに戻し、
    process_order.pyで再実行できる状態にリセットする。

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID
        timeout: タイムアウト秒数（呼び出し側への情報提供用）
        model: AIモデル（呼び出し側への情報提供用）
        verbose: 詳細ログ出力

    Returns:
        Dict: 結果情報
            - success: 成功したか
            - message: メッセージ
            - order: 更新後のORDER情報
            - previous_status: 変更前のステータス
            - new_status: 変更後のステータス

    Raises:
        ValidationError: 入力検証エラー
        DatabaseError: DB操作エラー
    """
    # 入力検証
    validate_project_name(project_id)
    validate_order_id(order_id)

    # 現在のORDER情報を事前取得（トランザクション外で検証してから更新）
    conn_check = get_connection()
    try:
        if not order_exists(conn_check, order_id, project_id):
            raise ValidationError(
                f"ORDERが見つかりません: {order_id} (project: {project_id})",
                "order_id",
                order_id
            )

        current = fetch_one(
            conn_check,
            "SELECT * FROM orders WHERE id = ? AND project_id = ?",
            (order_id, project_id)
        )
    finally:
        conn_check.close()

    if not current:
        raise ValidationError(
            f"ORDERが見つかりません: {order_id} (project: {project_id})",
            "order_id",
            order_id
        )

    current_dict = dict(current)
    previous_status = current_dict["status"]

    if verbose:
        print(f"[retry_order] ORDER: {order_id}, 現在のステータス: {previous_status}", file=sys.stderr)

    # 既にPLANNINGであれば何もしない
    if previous_status == "PLANNING":
        return {
            "success": True,
            "message": f"ORDERは既にPLANNINGステータスです: {order_id}",
            "order": current_dict,
            "previous_status": previous_status,
            "new_status": previous_status,
            "changed": False,
        }

    # 再実行可能なステータスか確認
    if previous_status not in RETRYABLE_STATUSES:
        raise ValidationError(
            f"ORDERを再実行できません。再実行可能なステータス: {', '.join(RETRYABLE_STATUSES)}\n"
            f"現在のステータス: {previous_status}",
            "status",
            previous_status
        )

    now = datetime.now().isoformat()
    new_status = "PLANNING"

    with transaction() as conn:
        # ORDERステータスをPLANNINGに直接更新（状態遷移テーブルをバイパス）
        # PLANNING_FAILED → PLANNING は通常の遷移テーブルにない特殊遷移のため
        execute_query(
            conn,
            """
            UPDATE orders
            SET status = ?, updated_at = ?
            WHERE id = ? AND project_id = ?
            """,
            (new_status, now, order_id, project_id)
        )

        # 変更履歴を記録
        reason = f"ORDER再実行: {previous_status} → {new_status} (model={model}, timeout={timeout})"
        execute_query(
            conn,
            """
            INSERT INTO change_history (
                entity_type, entity_id, field_name,
                old_value, new_value, changed_by, change_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("order", order_id, "status", previous_status, new_status, "System", reason)
        )

        # 更新後のORDERを取得（複合キー対応）
        updated = fetch_one(
            conn,
            "SELECT * FROM orders WHERE id = ? AND project_id = ?",
            (order_id, project_id)
        )

        result_order = row_to_dict(updated)

    if verbose:
        print(f"[retry_order] ステータス変更完了: {previous_status} → {new_status}", file=sys.stderr)

    return {
        "success": True,
        "message": f"ORDERを再実行可能な状態にリセットしました: {order_id} ({previous_status} → {new_status})",
        "order": result_order,
        "previous_status": previous_status,
        "new_status": new_status,
        "changed": True,
    }


def main():
    """CLI エントリーポイント"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from config import setup_utf8_output
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="ORDERを再実行可能な状態にリセット",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("order_id", help="ORDER ID")
    parser.add_argument("--timeout", type=int, default=600, help="タイムアウト秒数（デフォルト: 600）")
    parser.add_argument("--model", default="sonnet", help="AIモデル（haiku/sonnet/opus）")
    parser.add_argument("--verbose", action="store_true", help="詳細ログ出力")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    try:
        result = retry_order(
            args.project_id,
            args.order_id,
            timeout=args.timeout,
            model=args.model,
            verbose=args.verbose,
        )

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            if result.get("changed"):
                print(f"ORDERを再実行可能な状態にリセットしました: {args.order_id}")
                print(f"  ステータス: {result['previous_status']} → {result['new_status']}")
            else:
                print(result["message"])

    except (ValidationError, DatabaseError) as e:
        if args.json:
            print(json.dumps({
                "success": False,
                "message": str(e),
                "error": str(e),
            }, ensure_ascii=False, indent=2))
        else:
            print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        if args.json:
            print(json.dumps({
                "success": False,
                "message": f"予期しないエラー: {e}",
                "error": str(e),
            }, ensure_ascii=False, indent=2))
        else:
            print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
