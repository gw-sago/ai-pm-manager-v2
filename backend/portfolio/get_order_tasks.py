#!/usr/bin/env python3
"""
AI PM Framework - ORDER関連タスク一覧取得

指定されたORDERのタスク一覧を取得します。

Usage:
    python backend/portfolio/get_order_tasks.py PROJECT_ID ORDER_ID [options]

Options:
    --json          JSON形式で出力（デフォルト）

Example:
    python backend/portfolio/get_order_tasks.py ai_pm_manager ORDER_068
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Any


# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import (
    get_connection, fetch_all, rows_to_dicts, DatabaseError
)


def get_order_tasks(
    project_id: str,
    order_id: str,
) -> List[Dict[str, Any]]:
    """
    指定されたORDERのタスク一覧を取得

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID

    Returns:
        タスク一覧
    """
    # クエリ構築
    query = """
    SELECT
        t.id,
        t.order_id,
        t.project_id,
        t.title,
        t.description,
        t.status,
        t.priority,
        t.assignee,
        t.recommended_model,
        t.started_at,
        t.completed_at,
        t.created_at,
        t.updated_at
    FROM tasks t
    WHERE t.project_id = ? AND t.order_id = ?
    ORDER BY
        CASE t.status
            WHEN 'IN_PROGRESS' THEN 0
            WHEN 'REWORK' THEN 1
            WHEN 'QUEUED' THEN 2
            WHEN 'BLOCKED' THEN 3
            WHEN 'DONE' THEN 4
            WHEN 'COMPLETED' THEN 5
        END,
        CASE t.priority
            WHEN 'P0' THEN 0
            WHEN 'P1' THEN 1
            WHEN 'P2' THEN 2
        END,
        t.created_at
    """

    conn = get_connection()
    try:
        rows = fetch_all(conn, query, (project_id, order_id))
        tasks = rows_to_dicts(rows)

        # 依存関係を取得
        result_tasks = []
        for task in tasks:
            task_id = task["id"]

            # 依存関係を取得
            deps_query = """
            SELECT depends_on_task_id
            FROM task_dependencies
            WHERE task_id = ? AND project_id = ?
            """
            deps_rows = fetch_all(conn, deps_query, (task_id, project_id))
            depends_on = [row["depends_on_task_id"] for row in deps_rows]

            result_tasks.append({
                "id": task_id,
                "orderId": task["order_id"],
                "projectId": task["project_id"],
                "title": task["title"],
                "description": task["description"],
                "status": task["status"],
                "priority": task["priority"],
                "assignee": task["assignee"],
                "recommendedModel": task["recommended_model"],
                "dependsOn": depends_on,
                "startedAt": task["started_at"],
                "completedAt": task["completed_at"],
                "createdAt": task["created_at"],
                "updatedAt": task["updated_at"],
            })

        return result_tasks

    finally:
        conn.close()


def main():
    """CLI エントリーポイント"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
        setup_utf8_output()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(
        description="ORDER関連タスク一覧を取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("order_id", help="ORDER ID")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力（デフォルト）")

    args = parser.parse_args()

    try:
        tasks = get_order_tasks(args.project_id, args.order_id)

        output = {
            "success": True,
            "projectId": args.project_id,
            "orderId": args.order_id,
            "count": len(tasks),
            "tasks": tasks,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))

    except DatabaseError as e:
        print(json.dumps({
            "success": False,
            "error": str(e),
        }, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(json.dumps({
            "success": False,
            "error": f"予期しないエラー: {e}",
        }, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
