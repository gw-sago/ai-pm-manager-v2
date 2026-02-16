#!/usr/bin/env python3
"""
AI PM Framework - タスク一覧取得スクリプト

Usage:
    python backend/task/list.py PROJECT_NAME [options]

Options:
    --order         ORDER IDでフィルタ
    --status        ステータスでフィルタ（カンマ区切りで複数指定可）
    --assignee      担当者でフィルタ
    --priority      優先度でフィルタ
    --active        アクティブなタスクのみ（QUEUED/BLOCKED/IN_PROGRESS/DONE/REWORK）
    --pending       未完了タスクのみ（COMPLETED以外）
    --blocked       BLOCKEDタスクのみ
    --limit         取得件数制限
    --json          JSON形式で出力（デフォルト）
    --table         テーブル形式で出力

Example:
    python backend/task/list.py AI_PM_PJ
    python backend/task/list.py AI_PM_PJ --order ORDER_036
    python backend/task/list.py AI_PM_PJ --status IN_PROGRESS,DONE --table
    python backend/task/list.py AI_PM_PJ --active --assignee "Worker A"
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

# aipm-db は Python パッケージ名として使えないためモジュール直接参照
try:
    from aipm_db.utils.db import (
        get_connection, fetch_all, rows_to_dicts, DatabaseError
    )
    from aipm_db.utils.validation import (
        validate_project_name, validate_order_id, validate_status,
        project_exists, ValidationError
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from utils.db import (
        get_connection, fetch_all, rows_to_dicts, DatabaseError
    )
    from utils.validation import (
        validate_project_name, validate_order_id, validate_status,
        project_exists, ValidationError
    )


def list_tasks(
    project_id: str,
    *,
    order_id: Optional[str] = None,
    status: Optional[List[str]] = None,
    assignee: Optional[str] = None,
    priority: Optional[str] = None,
    active_only: bool = False,
    pending_only: bool = False,
    blocked_only: bool = False,
    limit: Optional[int] = None,
    include_dependencies: bool = True,
) -> List[Dict[str, Any]]:
    """
    タスク一覧を取得

    Args:
        project_id: プロジェクトID
        order_id: ORDER IDでフィルタ
        status: ステータスでフィルタ（リスト）
        assignee: 担当者でフィルタ
        priority: 優先度でフィルタ
        active_only: アクティブなタスクのみ
        pending_only: 未完了タスクのみ
        blocked_only: BLOCKEDタスクのみ
        limit: 取得件数制限
        include_dependencies: 依存関係を含めるか

    Returns:
        タスクのリスト

    Raises:
        ValidationError: 入力検証エラー
        DatabaseError: DB操作エラー
    """
    # 入力検証
    validate_project_name(project_id)

    if order_id:
        validate_order_id(order_id)

    if status:
        for s in status:
            validate_status(s, "task")

    # クエリ構築（複合キー対応）
    query = """
    SELECT
        t.id,
        t.order_id,
        t.title,
        t.description,
        t.status,
        t.assignee,
        t.priority,
        t.recommended_model,
        t.started_at,
        t.completed_at,
        t.created_at,
        t.updated_at,
        o.title as order_title
    FROM tasks t
    JOIN orders o ON t.order_id = o.id AND t.project_id = o.project_id
    WHERE t.project_id = ?
    """
    params = [project_id]

    # ORDER フィルタ
    if order_id:
        query += " AND t.order_id = ?"
        params.append(order_id)

    # ステータスフィルタ
    if status:
        placeholders = ", ".join(["?" for _ in status])
        query += f" AND t.status IN ({placeholders})"
        params.extend(status)
    elif active_only:
        query += " AND t.status IN ('QUEUED', 'BLOCKED', 'IN_PROGRESS', 'DONE', 'REWORK')"
    elif pending_only:
        query += " AND t.status != 'COMPLETED'"
    elif blocked_only:
        query += " AND t.status = 'BLOCKED'"

    # 担当者フィルタ
    if assignee:
        query += " AND t.assignee = ?"
        params.append(assignee)

    # 優先度フィルタ
    if priority:
        query += " AND t.priority = ?"
        params.append(priority)

    # ソート
    query += """
    ORDER BY
        CASE t.status
            WHEN 'IN_PROGRESS' THEN 0
            WHEN 'REWORK' THEN 1
            WHEN 'DONE' THEN 2
            WHEN 'QUEUED' THEN 3
            WHEN 'BLOCKED' THEN 4
            WHEN 'INTERRUPTED' THEN 5
            WHEN 'COMPLETED' THEN 6
        END,
        CASE t.priority
            WHEN 'P0' THEN 0
            WHEN 'P1' THEN 1
            WHEN 'P2' THEN 2
        END,
        t.created_at
    """

    # 件数制限
    if limit:
        query += " LIMIT ?"
        params.append(limit)

    conn = get_connection()
    try:
        rows = fetch_all(conn, query, tuple(params))
        tasks = rows_to_dicts(rows)

        # 依存関係を追加（複合キー対応）
        if include_dependencies:
            for task in tasks:
                deps = fetch_all(
                    conn,
                    """
                    SELECT depends_on_task_id
                    FROM task_dependencies
                    WHERE task_id = ? AND project_id = ?
                    """,
                    (task["id"], project_id)
                )
                task["depends_on"] = [d["depends_on_task_id"] for d in deps]

        return tasks

    finally:
        conn.close()


def format_table(tasks: List[Dict[str, Any]]) -> str:
    """
    タスクリストをテーブル形式でフォーマット
    """
    if not tasks:
        return "タスクが見つかりません。"

    # ヘッダー
    lines = [
        "| Task ID | タイトル | ステータス | 担当 | 優先度 | 依存 | ORDER |",
        "|---------|----------|------------|------|--------|------|-------|"
    ]

    for t in tasks:
        deps = ", ".join(t.get("depends_on", [])) or "-"
        assignee = t.get("assignee") or "-"
        lines.append(
            f"| {t['id']} | {t['title'][:20]} | {t['status']} | {assignee} | {t['priority']} | {deps[:20]} | {t['order_id']} |"
        )

    return "\n".join(lines)


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
        description="タスク一覧を取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("--order", help="ORDER IDでフィルタ")
    parser.add_argument("--status", help="ステータスでフィルタ（カンマ区切り）")
    parser.add_argument("--assignee", help="担当者でフィルタ")
    parser.add_argument("--priority", help="優先度でフィルタ")
    parser.add_argument("--active", action="store_true", help="アクティブなタスクのみ")
    parser.add_argument("--pending", action="store_true", help="未完了タスクのみ")
    parser.add_argument("--blocked", action="store_true", help="BLOCKEDタスクのみ")
    parser.add_argument("--limit", type=int, help="取得件数制限")
    parser.add_argument("--table", action="store_true", help="テーブル形式で出力")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    # ステータスのパース
    status_list = None
    if args.status:
        status_list = [s.strip() for s in args.status.split(",") if s.strip()]

    try:
        tasks = list_tasks(
            args.project_id,
            order_id=args.order,
            status=status_list,
            assignee=args.assignee,
            priority=args.priority,
            active_only=args.active,
            pending_only=args.pending,
            blocked_only=args.blocked,
            limit=args.limit,
        )

        if args.table:
            print(format_table(tasks))
        else:
            # デフォルトはJSON
            print(json.dumps(tasks, ensure_ascii=False, indent=2, default=str))

    except (ValidationError, DatabaseError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
