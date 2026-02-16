#!/usr/bin/env python3
"""
AI PM Framework - バックログ詳細取得スクリプト

Usage:
    python backend/backlog/get.py PROJECT_NAME BACKLOG_ID [options]

Options:
    --json          JSON形式で出力（デフォルト）
    --detail        詳細情報を含める（履歴等）

Example:
    python backend/backlog/get.py AI_PM_PJ BACKLOG_081
    python backend/backlog/get.py ai_pm_manager BACKLOG_081 --json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any

# aipm-db は Python パッケージ名として使えないためモジュール直接参照
try:
    from aipm_db.utils.db import (
        get_connection, fetch_one, fetch_all, row_to_dict, rows_to_dicts,
        DatabaseError
    )
    from aipm_db.utils.validation import (
        validate_project_name, validate_backlog_id,
        backlog_exists, ValidationError
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from utils.db import (
        get_connection, fetch_one, fetch_all, row_to_dict, rows_to_dicts,
        DatabaseError
    )
    from utils.validation import (
        validate_project_name, validate_backlog_id,
        backlog_exists, ValidationError
    )


def get_backlog(
    project_id: str,
    backlog_id: str,
    *,
    include_history: bool = False,
    include_order_details: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    バックログ詳細を取得

    Args:
        project_id: プロジェクトID
        backlog_id: バックログID
        include_history: 変更履歴を含めるか
        include_order_details: ORDER詳細を含めるか

    Returns:
        バックログ詳細（見つからない場合はNone）

    Raises:
        ValidationError: 入力検証エラー
        DatabaseError: DB操作エラー
    """
    # 入力検証
    validate_project_name(project_id)
    validate_backlog_id(backlog_id)

    conn = get_connection()
    try:
        # バックログ取得
        backlog_row = fetch_one(
            conn,
            """
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
                b.completed_at
            FROM backlog_items b
            WHERE b.id = ? AND b.project_id = ?
            """,
            (backlog_id, project_id)
        )

        if not backlog_row:
            return None

        backlog = row_to_dict(backlog_row)

        # ORDER詳細を取得
        if include_order_details and backlog.get("related_order_id"):
            order = fetch_one(
                conn,
                """
                SELECT
                    o.id,
                    o.title,
                    o.status,
                    o.project_id as order_project_id,
                    o.created_at as order_created_at,
                    o.updated_at as order_updated_at
                FROM orders o
                WHERE o.id = ?
                """,
                (backlog["related_order_id"],)
            )
            if order:
                backlog["order"] = row_to_dict(order)

                # タスク統計を取得
                task_stats = fetch_one(
                    conn,
                    """
                    SELECT
                        COUNT(*) as total_tasks,
                        SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed_tasks,
                        SUM(CASE WHEN status = 'IN_PROGRESS' THEN 1 ELSE 0 END) as in_progress_tasks,
                        SUM(CASE WHEN status = 'BLOCKED' THEN 1 ELSE 0 END) as blocked_tasks
                    FROM tasks
                    WHERE order_id = ? AND project_id = ?
                    """,
                    (backlog["related_order_id"], order["order_project_id"])
                )
                if task_stats:
                    total = task_stats["total_tasks"] or 0
                    completed = task_stats["completed_tasks"] or 0
                    backlog["total_tasks"] = total
                    backlog["completed_tasks"] = completed
                    backlog["in_progress_tasks"] = task_stats["in_progress_tasks"] or 0
                    backlog["blocked_tasks"] = task_stats["blocked_tasks"] or 0
                    backlog["progress_percent"] = round(completed / total * 100, 1) if total > 0 else 0
            else:
                backlog["order"] = None

        # 変更履歴を取得
        if include_history:
            history = fetch_all(
                conn,
                """
                SELECT
                    field_name,
                    old_value,
                    new_value,
                    changed_by,
                    change_reason,
                    changed_at
                FROM change_history
                WHERE entity_type = 'backlog' AND entity_id = ?
                ORDER BY changed_at DESC
                LIMIT 20
                """,
                (backlog_id,)
            )
            backlog["history"] = rows_to_dicts(history)

        return backlog

    finally:
        conn.close()


def format_detail(backlog: Dict[str, Any]) -> str:
    """
    バックログ詳細を読みやすい形式でフォーマット
    """
    lines = [
        f"# {backlog['id']}: {backlog['title']}",
        "",
        "## 基本情報",
        f"- **プロジェクト**: {backlog['project_id']}",
        f"- **ステータス**: {backlog['status']}",
        f"- **優先度**: {backlog['priority']}",
        "",
    ]

    if backlog.get("description"):
        lines.extend([
            "## 説明",
            backlog["description"],
            "",
        ])

    # ORDER情報
    if backlog.get("related_order_id"):
        lines.append("## 紐付けORDER")
        lines.append(f"- **ORDER ID**: {backlog['related_order_id']}")
        if backlog.get("order"):
            order = backlog["order"]
            lines.append(f"- **タイトル**: {order.get('title', '-')}")
            lines.append(f"- **ステータス**: {order.get('status', '-')}")
        if backlog.get("total_tasks", 0) > 0:
            lines.append(f"- **タスク進捗**: {backlog['completed_tasks']}/{backlog['total_tasks']} ({backlog['progress_percent']}%)")
        lines.append("")
    else:
        lines.extend([
            "## 紐付けORDER",
            "- 未着手（ORDERなし）",
            "",
        ])

    # タイムスタンプ
    lines.extend([
        "## タイムスタンプ",
        f"- **作成日時**: {backlog['created_at']}",
        f"- **更新日時**: {backlog['updated_at']}",
        f"- **完了日時**: {backlog.get('completed_at') or '-'}",
        "",
    ])

    # 変更履歴
    if backlog.get("history"):
        lines.append("## 変更履歴（最新20件）")
        for h in backlog["history"]:
            lines.append(
                f"- {h['changed_at']}: {h['field_name']} "
                f"({h.get('old_value') or '-'} → {h.get('new_value') or '-'}) "
                f"by {h['changed_by']}"
            )
        lines.append("")

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
        description="バックログ詳細を取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("backlog_id", help="バックログID")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    parser.add_argument("--detail", action="store_true", help="詳細情報を含める（履歴等）")

    args = parser.parse_args()

    try:
        backlog = get_backlog(
            args.project_id,
            args.backlog_id,
            include_history=args.detail,
            include_order_details=True,
        )

        if not backlog:
            # JSON形式でエラーを返す（スクリプト連携用）
            error_response = {
                "success": False,
                "error": f"バックログが見つかりません: {args.backlog_id} (project: {args.project_id})"
            }
            if args.json:
                print(json.dumps(error_response, ensure_ascii=False, indent=2))
            else:
                print(f"エラー: {error_response['error']}", file=sys.stderr)
            sys.exit(1)

        if args.json:
            # success フラグを追加
            output = {
                "success": True,
                **backlog
            }
            print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
        else:
            print(format_detail(backlog))

    except (ValidationError, DatabaseError) as e:
        error_response = {
            "success": False,
            "error": str(e)
        }
        if args.json:
            print(json.dumps(error_response, ensure_ascii=False, indent=2))
        else:
            print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        error_response = {
            "success": False,
            "error": f"予期しないエラー: {e}"
        }
        if args.json:
            print(json.dumps(error_response, ensure_ascii=False, indent=2))
        else:
            print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
