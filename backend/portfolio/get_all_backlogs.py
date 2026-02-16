#!/usr/bin/env python3
"""
AI PM Framework - 全プロジェクト統合バックログ一覧取得

複数プロジェクトのバックログを統合して「PJ名/BACKLOG番号」形式で取得します。

Usage:
    python backend/portfolio/get_all_backlogs.py [options]

Options:
    --status        ステータスでフィルタ（カンマ区切りで複数指定可）
    --priority      優先度でフィルタ
    --limit         取得件数制限
    --json          JSON形式で出力（デフォルト）

Example:
    python backend/portfolio/get_all_backlogs.py
    python backend/portfolio/get_all_backlogs.py --status TODO,IN_PROGRESS
    python backend/portfolio/get_all_backlogs.py --priority High
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
    get_connection, fetch_all, rows_to_dicts, DatabaseError
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


def get_all_backlogs(
    *,
    status: Optional[List[str]] = None,
    priority: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    全プロジェクトのバックログ一覧を統合取得

    Args:
        status: ステータスでフィルタ（リスト）
        priority: 優先度でフィルタ
        limit: 取得件数制限

    Returns:
        統合バックログ一覧（portfolioId付き）
    """
    # クエリ構築
    query = """
    SELECT
        b.id,
        b.project_id,
        b.title,
        b.description,
        b.priority,
        b.status,
        b.related_order_id,
        b.created_at,
        b.updated_at,
        b.completed_at,
        p.name as project_name
    FROM backlog_items b
    JOIN projects p ON b.project_id = p.id
    WHERE 1=1
    """
    params: List[Any] = []

    # ステータスフィルタ
    if status:
        placeholders = ", ".join(["?" for _ in status])
        query += f" AND b.status IN ({placeholders})"
        params.extend(status)

    # 優先度フィルタ
    if priority:
        query += " AND b.priority = ?"
        params.append(priority)

    # ソート（優先度順、ステータス順、作成日順）
    query += """
    ORDER BY
        b.project_id,
        CASE b.priority
            WHEN 'High' THEN 0
            WHEN 'Medium' THEN 1
            WHEN 'Low' THEN 2
        END,
        CASE b.status
            WHEN 'IN_PROGRESS' THEN 0
            WHEN 'TODO' THEN 1
            WHEN 'DONE' THEN 2
        END,
        b.created_at DESC
    """

    # 件数制限
    if limit:
        query += " LIMIT ?"
        params.append(limit)

    conn = get_connection()
    try:
        rows = fetch_all(conn, query, tuple(params) if params else None)
        backlogs = rows_to_dicts(rows)

        # ポートフォリオ形式に変換
        portfolio_backlogs = []
        for backlog in backlogs:
            project_id = backlog["project_id"]
            backlog_id = backlog["id"]

            portfolio_backlogs.append({
                "portfolioId": f"{project_id}/{backlog_id}",
                "projectId": project_id,
                "projectPrefix": get_project_prefix(project_id),
                "projectName": backlog["project_name"],
                "id": backlog_id,
                "title": backlog["title"],
                "description": backlog["description"],
                "status": backlog["status"],
                "priority": backlog["priority"],
                "relatedOrderId": backlog["related_order_id"],
                "createdAt": backlog["created_at"],
                "updatedAt": backlog["updated_at"],
                "completedAt": backlog["completed_at"],
            })

        return portfolio_backlogs

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
        description="全プロジェクトのバックログ一覧を統合取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("--status", help="ステータスでフィルタ（カンマ区切り）")
    parser.add_argument("--priority", help="優先度でフィルタ")
    parser.add_argument("--limit", type=int, help="取得件数制限")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力（デフォルト）")

    args = parser.parse_args()

    # ステータスのパース
    status_list = None
    if args.status:
        status_list = [s.strip() for s in args.status.split(",") if s.strip()]

    try:
        backlogs = get_all_backlogs(
            status=status_list,
            priority=args.priority,
            limit=args.limit,
        )

        output = {
            "success": True,
            "count": len(backlogs),
            "backlogs": backlogs,
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
