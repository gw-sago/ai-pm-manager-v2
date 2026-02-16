#!/usr/bin/env python3
"""
AI PM Framework - ORDER リリース実行スクリプト

ORDER完了後のリリース処理を実行する。
内部的に git_release.py の execute_git_release() を呼び出す。

使用例:
    python release_order.py ai_pm_manager ORDER_079
    python release_order.py ai_pm_manager ORDER_079 --dry-run
    python release_order.py ai_pm_manager ORDER_079 --json
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

# 親パッケージからインポート
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import setup_utf8_output
from utils.db import get_connection, fetch_one, fetch_all

# UTF-8出力設定
setup_utf8_output()


def validate_order_status(project_id: str, order_id: str) -> Dict[str, Any]:
    """
    ORDER状態を検証（全タスクがCOMPLETED/DONEであることを確認）

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID

    Returns:
        検証結果
    """
    conn = get_connection()

    # ORDERを取得
    order = fetch_one(
        conn,
        "SELECT id, project_id, title, status, completed_at FROM orders WHERE id = ? AND project_id = ?",
        (order_id, project_id),
    )

    if not order:
        conn.close()
        return {
            "success": False,
            "error": f"ORDER {order_id} not found",
        }

    order_dict = dict(order)

    # 全タスクがCOMPLETED/DONEであることを確認
    tasks = fetch_all(
        conn,
        "SELECT id, status FROM tasks WHERE order_id = ? AND project_id = ?",
        (order_id, project_id),
    )
    conn.close()

    incomplete = [
        dict(t) for t in tasks
        if t["status"] not in ("COMPLETED", "DONE", "CANCELLED", "REJECTED", "SKIPPED")
    ]

    if incomplete:
        task_summary = ", ".join(f"{t['id']}({t['status']})" for t in incomplete[:5])
        return {
            "success": False,
            "error": f"ORDER {order_id} has incomplete tasks: {task_summary}",
            "order": order_dict,
        }

    return {
        "success": True,
        "order": order_dict,
    }


def get_related_backlog(project_id: str, order_id: str) -> List[Dict[str, Any]]:
    """
    関連BACKLOGを取得

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID

    Returns:
        BACKLOG項目リスト
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title, status
        FROM backlog_items
        WHERE project_id = ? AND related_order_id = ?
    """, (project_id, order_id))

    backlog_items = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return backlog_items


def execute_release(
    project_id: str,
    order_id: str,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    リリース処理を実行（git_release.py のラッパー）

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID
        dry_run: ドライランモード

    Returns:
        実行結果
    """
    from release.git_release import execute_git_release

    return execute_git_release(
        project_id=project_id,
        order_ids=[order_id],
        dry_run=dry_run,
    )


def format_output(result: Dict[str, Any], json_output: bool = False) -> str:
    """結果をフォーマット"""
    if json_output:
        return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    if not result.get("success"):
        return f"Error: {result.get('error', 'unknown error')}"

    from release.git_release import format_output as git_format
    return git_format(result, json_output=False)


def main():
    parser = argparse.ArgumentParser(
        description="ORDERリリース処理を実行",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
    # リリース実行
    python release_order.py ai_pm_manager ORDER_079

    # ドライラン（変更なし）
    python release_order.py ai_pm_manager ORDER_079 --dry-run

    # JSON形式で出力
    python release_order.py ai_pm_manager ORDER_079 --json
        """
    )

    parser.add_argument(
        "project_id",
        help="プロジェクトID（例: ai_pm_manager）"
    )
    parser.add_argument(
        "order_id",
        help="ORDER ID（例: ORDER_079）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="ドライランモード（変更を行わない）"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )

    args = parser.parse_args()

    try:
        result = execute_release(
            project_id=args.project_id,
            order_id=args.order_id,
            dry_run=args.dry_run,
        )

        output = format_output(result, json_output=args.json)
        print(output)

        sys.exit(0 if result.get("success") else 1)

    except Exception as e:
        if args.json:
            print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        else:
            print(f"エラー: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
