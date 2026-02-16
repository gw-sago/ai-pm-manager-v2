#!/usr/bin/env python3
"""
AI PM Framework - 依存関係状態取得API

task_dependenciesテーブルから依存関係を取得し、各タスクのブロック状態を判定します。

Usage:
    python backend/portfolio/dependency_status.py PROJECT_ID [TASK_ID] [options]

Options:
    --all             指定プロジェクトの全タスクの依存関係状態を取得
    --order ORDER_ID  指定ORDERの全タスクの依存関係状態を取得
    --json            JSON形式で出力（デフォルト）

Example:
    # 特定タスクの依存関係状態を取得
    python backend/portfolio/dependency_status.py ai_pm_manager TASK_1101

    # プロジェクト全体の依存関係状態を取得
    python backend/portfolio/dependency_status.py ai_pm_manager --all

    # 特定ORDERの依存関係状態を取得
    python backend/portfolio/dependency_status.py ai_pm_manager --order ORDER_122
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional


# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import (
    get_connection, fetch_all, fetch_one, rows_to_dicts, DatabaseError
)


# 完了とみなされるステータス
COMPLETED_STATUSES = {'COMPLETED', 'DONE', 'SKIPPED'}


def get_task_dependency_status(
    project_id: str,
    task_id: str,
) -> Dict[str, Any]:
    """
    指定タスクの依存関係状態を取得

    Args:
        project_id: プロジェクトID
        task_id: タスクID

    Returns:
        依存関係状態情報:
        {
            "task_id": "TASK_1101",
            "project_id": "ai_pm_manager",
            "status": "QUEUED",
            "is_blocked": True/False,
            "dependencies": [
                {
                    "task_id": "TASK_1100",
                    "title": "依存タスクタイトル",
                    "status": "COMPLETED",
                    "is_completed": True/False
                },
                ...
            ],
            "completed_count": 1,
            "total_count": 2,
            "completion_rate": 0.5
        }

    Raises:
        DatabaseError: タスクが見つからない場合
    """
    conn = get_connection()
    try:
        # タスク情報を取得
        task_query = """
        SELECT id, title, status, project_id
        FROM tasks
        WHERE id = ? AND project_id = ?
        """
        task_row = fetch_one(conn, task_query, (task_id, project_id))

        if not task_row:
            raise DatabaseError(f"タスクが見つかりません: {task_id} (project: {project_id})")

        task = dict(task_row)

        # 依存関係を取得
        deps_query = """
        SELECT
            td.depends_on_task_id,
            t.title,
            t.status
        FROM task_dependencies td
        JOIN tasks t ON td.depends_on_task_id = t.id AND td.project_id = t.project_id
        WHERE td.task_id = ? AND td.project_id = ?
        """
        deps_rows = fetch_all(conn, deps_query, (task_id, project_id))
        dependencies = []
        completed_count = 0

        for row in deps_rows:
            dep_status = row["status"]
            is_completed = dep_status in COMPLETED_STATUSES
            if is_completed:
                completed_count += 1

            dependencies.append({
                "task_id": row["depends_on_task_id"],
                "title": row["title"],
                "status": dep_status,
                "is_completed": is_completed,
            })

        total_count = len(dependencies)
        completion_rate = completed_count / total_count if total_count > 0 else 1.0
        is_blocked = total_count > 0 and completed_count < total_count

        return {
            "task_id": task_id,
            "project_id": project_id,
            "status": task["status"],
            "title": task["title"],
            "is_blocked": is_blocked,
            "dependencies": dependencies,
            "completed_count": completed_count,
            "total_count": total_count,
            "completion_rate": completion_rate,
        }

    finally:
        conn.close()


def get_all_tasks_dependency_status(
    project_id: str,
    order_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    プロジェクト全体（またはORDER単位）のタスク依存関係状態を取得

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID（Noneの場合はプロジェクト全体）

    Returns:
        タスクごとの依存関係状態のリスト
    """
    conn = get_connection()
    try:
        # タスク一覧を取得
        if order_id:
            tasks_query = """
            SELECT id, title, status, project_id
            FROM tasks
            WHERE project_id = ? AND order_id = ?
            ORDER BY id
            """
            tasks_rows = fetch_all(conn, tasks_query, (project_id, order_id))
        else:
            tasks_query = """
            SELECT id, title, status, project_id
            FROM tasks
            WHERE project_id = ?
            ORDER BY id
            """
            tasks_rows = fetch_all(conn, tasks_query, (project_id,))

        results = []

        for task_row in tasks_rows:
            task_id = task_row["id"]

            # 各タスクの依存関係状態を取得
            status_info = get_task_dependency_status(project_id, task_id)
            results.append(status_info)

        return results

    finally:
        conn.close()


def get_blocking_tasks(
    project_id: str,
    order_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    ブロックされているタスク一覧を取得

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID（Noneの場合はプロジェクト全体）

    Returns:
        ブロックされているタスクの依存関係状態のリスト
    """
    all_statuses = get_all_tasks_dependency_status(project_id, order_id)
    return [status for status in all_statuses if status["is_blocked"]]


def main():
    """CLI エントリーポイント"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
        setup_utf8_output()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(
        description="タスク依存関係の状態を取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("task_id", nargs="?", help="タスクID（--all や --order と併用しない場合は必須）")
    parser.add_argument("--all", action="store_true", help="プロジェクト全体の依存関係状態を取得")
    parser.add_argument("--order", help="指定ORDERの依存関係状態を取得")
    parser.add_argument("--blocked-only", action="store_true", help="ブロックされているタスクのみ表示")
    parser.add_argument("--json", action="store_true", default=True, help="JSON形式で出力（デフォルト）")

    args = parser.parse_args()

    # 引数検証
    if not args.all and not args.order and not args.task_id:
        parser.error("task_id を指定するか、--all または --order オプションを使用してください")

    if args.task_id and (args.all or args.order):
        parser.error("task_id と --all/--order は同時に指定できません")

    try:
        if args.task_id:
            # 単一タスクの依存関係状態を取得
            result = get_task_dependency_status(args.project_id, args.task_id)
            output = {
                "success": True,
                "project_id": args.project_id,
                "task_id": args.task_id,
                "dependency_status": result,
            }
        else:
            # 複数タスクの依存関係状態を取得
            if args.blocked_only:
                results = get_blocking_tasks(args.project_id, args.order)
            else:
                results = get_all_tasks_dependency_status(args.project_id, args.order)

            output = {
                "success": True,
                "project_id": args.project_id,
                "order_id": args.order,
                "count": len(results),
                "blocked_count": sum(1 for r in results if r["is_blocked"]),
                "tasks": results,
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
