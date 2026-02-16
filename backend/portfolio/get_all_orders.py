#!/usr/bin/env python3
"""
AI PM Framework - 全プロジェクト統合ORDER一覧取得

複数プロジェクトのORDERを統合して「PJ名/ORDER番号」形式で取得します。

Usage:
    python backend/portfolio/get_all_orders.py [options]

Options:
    --status        ステータスでフィルタ（カンマ区切りで複数指定可）
    --active        アクティブなORDERのみ
    --limit         取得件数制限
    --json          JSON形式で出力（デフォルト）

Example:
    python backend/portfolio/get_all_orders.py
    python backend/portfolio/get_all_orders.py --active
    python backend/portfolio/get_all_orders.py --status IN_PROGRESS,PLANNING
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any


# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import (
    get_connection, fetch_all, fetch_one, rows_to_dicts, DatabaseError
)


# プロジェクト名からプレフィックスを生成
PROJECT_PREFIXES = {
    "ai_pm_manager": "APM",
    "AI_PM_PJ": "AIPM",
    "JERA_RSOC": "JERA",
}


def get_project_prefix(project_id: str) -> str:
    """プロジェクトIDからプレフィックスを取得"""
    return PROJECT_PREFIXES.get(project_id, project_id[:4].upper())


def get_all_orders(
    *,
    status: Optional[List[str]] = None,
    active_only: bool = False,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    全プロジェクトのORDER一覧を統合取得

    Args:
        status: ステータスでフィルタ（リスト）
        active_only: アクティブなORDERのみ
        limit: 取得件数制限

    Returns:
        統合ORDER一覧（portfolioId付き）
    """
    # クエリ構築
    query = """
    SELECT
        o.id,
        o.project_id,
        o.title,
        o.priority,
        o.status,
        o.started_at,
        o.completed_at,
        o.created_at,
        o.updated_at,
        p.name as project_name
    FROM orders o
    JOIN projects p ON o.project_id = p.id
    WHERE 1=1
    """
    params: List[Any] = []

    # ステータスフィルタ
    if status:
        placeholders = ", ".join(["?" for _ in status])
        query += f" AND o.status IN ({placeholders})"
        params.extend(status)
    elif active_only:
        query += " AND o.status IN ('PLANNING', 'IN_PROGRESS', 'REVIEW')"

    # ソート（プロジェクト順、優先度順、ステータス順、作成日順）
    query += """
    ORDER BY
        o.project_id,
        CASE o.status
            WHEN 'IN_PROGRESS' THEN 0
            WHEN 'REVIEW' THEN 1
            WHEN 'PLANNING' THEN 2
            WHEN 'ON_HOLD' THEN 3
            WHEN 'COMPLETED' THEN 4
            WHEN 'CANCELLED' THEN 5
        END,
        CASE o.priority
            WHEN 'P0' THEN 0
            WHEN 'P1' THEN 1
            WHEN 'P2' THEN 2
        END,
        o.created_at DESC
    """

    # 件数制限
    if limit:
        query += " LIMIT ?"
        params.append(limit)

    conn = get_connection()
    try:
        rows = fetch_all(conn, query, tuple(params) if params else None)
        orders = rows_to_dicts(rows)

        # ポートフォリオ形式に変換
        portfolio_orders = []
        for order in orders:
            project_id = order["project_id"]
            order_id = order["id"]

            # タスク数を取得
            task_count = fetch_one(
                conn,
                "SELECT COUNT(*) as count FROM tasks WHERE order_id = ? AND project_id = ?",
                (order_id, project_id)
            )
            total_tasks = task_count["count"] if task_count else 0

            # 完了タスク数を取得
            completed_count = fetch_one(
                conn,
                "SELECT COUNT(*) as count FROM tasks WHERE order_id = ? AND project_id = ? AND status IN ('DONE', 'COMPLETED')",
                (order_id, project_id)
            )
            completed_tasks = completed_count["count"] if completed_count else 0

            # 進捗率計算
            progress = round((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0

            portfolio_orders.append({
                "portfolioId": f"{project_id}/{order_id}",
                "projectId": project_id,
                "projectPrefix": get_project_prefix(project_id),
                "projectName": order["project_name"],
                "id": order_id,
                "title": order["title"],
                "status": order["status"],
                "priority": order["priority"],
                "progress": progress,
                "totalTasks": total_tasks,
                "completedTasks": completed_tasks,
                "startedAt": order["started_at"],
                "completedAt": order["completed_at"],
                "createdAt": order["created_at"],
                "updatedAt": order["updated_at"],
            })

        return portfolio_orders

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
        description="全プロジェクトのORDER一覧を統合取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("--status", help="ステータスでフィルタ（カンマ区切り）")
    parser.add_argument("--active", action="store_true", help="アクティブなORDERのみ")
    parser.add_argument("--limit", type=int, help="取得件数制限")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力（デフォルト）")

    args = parser.parse_args()

    # ステータスのパース
    status_list = None
    if args.status:
        status_list = [s.strip() for s in args.status.split(",") if s.strip()]

    try:
        orders = get_all_orders(
            status=status_list,
            active_only=args.active,
            limit=args.limit,
        )

        output = {
            "success": True,
            "count": len(orders),
            "orders": orders,
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
