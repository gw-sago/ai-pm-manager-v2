#!/usr/bin/env python3
"""
AI PM Framework - プロジェクト削除スクリプト

Usage:
    python backend/project/delete.py PROJECT_ID [options]

Arguments:
    PROJECT_ID          プロジェクトID

Options:
    --force             アクティブORDERがあっても強制削除
    --json              JSON形式で出力

Example:
    python backend/project/delete.py Old_Project --json
    python backend/project/delete.py AI_PM_PJ --force --json
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
    get_connection, fetch_one, fetch_all, execute_query, transaction, DatabaseError
)
from utils.validation import (
    validate_project_name, validate_project_exists, ValidationError
)


def get_project_info(conn, project_id: str) -> Optional[Dict[str, Any]]:
    """プロジェクト情報を取得"""
    row = fetch_one(
        conn,
        """
        SELECT id, name, path, status, is_active, current_order_id,
               created_at, updated_at
        FROM projects
        WHERE id = ?
        """,
        (project_id,)
    )
    return dict(row) if row else None


def get_active_orders(conn, project_id: str):
    """アクティブORDER一覧を取得"""
    rows = fetch_all(
        conn,
        """
        SELECT id, title, status
        FROM orders
        WHERE project_id = ? AND status IN ('PLANNING', 'IN_PROGRESS')
        """,
        (project_id,)
    )
    return [dict(r) for r in rows]


def get_related_counts(conn, project_id: str) -> Dict[str, int]:
    """関連エンティティの件数を取得"""
    order_count = fetch_one(
        conn,
        "SELECT COUNT(*) as cnt FROM orders WHERE project_id = ?",
        (project_id,)
    )
    task_count = fetch_one(
        conn,
        "SELECT COUNT(*) as cnt FROM tasks WHERE project_id = ?",
        (project_id,)
    )
    backlog_count = fetch_one(
        conn,
        "SELECT COUNT(*) as cnt FROM backlog_items WHERE project_id = ?",
        (project_id,)
    )
    return {
        "orders": order_count["cnt"] if order_count else 0,
        "tasks": task_count["cnt"] if task_count else 0,
        "backlogs": backlog_count["cnt"] if backlog_count else 0,
    }


def delete_project(
    project_id: str,
    *,
    force: bool = False,
) -> Dict[str, Any]:
    """
    プロジェクトをDBから削除

    Args:
        project_id: プロジェクトID
        force: アクティブORDERがあっても強制削除

    Returns:
        削除結果

    Raises:
        ValidationError: プロジェクトが存在しない場合、アクティブORDERがある場合（forceなし）
        DatabaseError: DB操作エラー
    """
    validate_project_name(project_id)

    conn = get_connection()
    try:
        validate_project_exists(conn, project_id)

        project_info = get_project_info(conn, project_id)
        active_orders = get_active_orders(conn, project_id)
        related_counts = get_related_counts(conn, project_id)

        # アクティブORDERチェック
        if active_orders and not force:
            return {
                "success": False,
                "project_id": project_id,
                "message": f"アクティブなORDERが{len(active_orders)}件あります。--forceで強制削除できます。",
                "active_orders": active_orders,
                "error_type": "ActiveOrdersExist",
            }

        # 削除実行（CASCADE削除で関連データも削除される）
        with transaction(conn) as tx_conn:
            execute_query(
                tx_conn,
                "DELETE FROM projects WHERE id = ?",
                (project_id,)
            )

        return {
            "success": True,
            "project_id": project_id,
            "message": f"プロジェクト '{project_id}' を削除しました",
            "deleted_project": project_info,
            "deleted_counts": related_counts,
            "force_used": force,
        }

    finally:
        conn.close()


def main():
    """CLI エントリーポイント"""
    try:
        from config import setup_utf8_output
    except ImportError:
        from config import setup_utf8_output
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="プロジェクトをDBから削除",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("--force", action="store_true",
                        help="アクティブORDERがあっても強制削除")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    try:
        result = delete_project(
            args.project_id,
            force=args.force,
        )

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            if result["success"]:
                print(f"[OK] {result['message']}")
                counts = result.get("deleted_counts", {})
                print(f"  削除されたORDER: {counts.get('orders', 0)}件")
                print(f"  削除されたタスク: {counts.get('tasks', 0)}件")
                print(f"  削除されたバックログ: {counts.get('backlogs', 0)}件")
            else:
                print(f"[ERROR] {result['message']}", file=sys.stderr)
                if not args.json:
                    sys.exit(1)

    except ValidationError as e:
        error_result = {
            "success": False,
            "project_id": args.project_id,
            "message": str(e),
            "error_type": "ValidationError",
        }
        if args.json:
            print(json.dumps(error_result, ensure_ascii=False, indent=2))
        else:
            print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)

    except DatabaseError as e:
        error_result = {
            "success": False,
            "project_id": args.project_id,
            "message": str(e),
            "error_type": "DatabaseError",
        }
        if args.json:
            print(json.dumps(error_result, ensure_ascii=False, indent=2))
        else:
            print(f"DBエラー: {e}", file=sys.stderr)
        sys.exit(1)

    except Exception as e:
        error_result = {
            "success": False,
            "project_id": args.project_id,
            "message": str(e),
            "error_type": type(e).__name__,
        }
        if args.json:
            print(json.dumps(error_result, ensure_ascii=False, indent=2))
        else:
            print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
