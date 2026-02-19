#!/usr/bin/env python3
"""
AI PM Framework - タスク詳細取得スクリプト

Usage:
    python backend/task/get.py PROJECT_NAME TASK_ID [options]

Options:
    --json          JSON形式で出力（デフォルト）
    --detail        詳細情報を含める（履歴等）
    --no-deps       依存関係を含めない

Example:
    python backend/task/get.py AI_PM_PJ TASK_188
    python backend/task/get.py AI_PM_PJ TASK_188 --detail
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List

# aipm-db は Python パッケージ名として使えないためモジュール直接参照
try:
    from aipm_db.utils.db import (
        get_connection, fetch_one, fetch_all, row_to_dict, rows_to_dicts,
        DatabaseError
    )
    from aipm_db.utils.validation import (
        validate_project_name, validate_task_id,
        task_exists, ValidationError
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from utils.db import (
        get_connection, fetch_one, fetch_all, row_to_dict, rows_to_dicts,
        DatabaseError
    )
    from utils.validation import (
        validate_project_name, validate_task_id,
        task_exists, ValidationError
    )


def get_task(
    project_id: str,
    task_id: str,
    *,
    include_dependencies: bool = True,
    include_history: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    タスク詳細を取得

    Args:
        project_id: プロジェクトID
        task_id: タスクID
        include_dependencies: 依存関係を含めるか
        include_history: 変更履歴を含めるか

    Returns:
        タスク詳細（見つからない場合はNone）

    Raises:
        ValidationError: 入力検証エラー
        DatabaseError: DB操作エラー
    """
    # 入力検証
    validate_project_name(project_id)
    validate_task_id(task_id)

    conn = get_connection()
    try:
        # タスク取得（複合キー対応）
        task_row = fetch_one(
            conn,
            """
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
                o.title as order_title,
                t.project_id
            FROM tasks t
            JOIN orders o ON t.order_id = o.id AND t.project_id = o.project_id
            WHERE t.id = ? AND t.project_id = ?
            """,
            (task_id, project_id)
        )

        if not task_row:
            return None

        task = row_to_dict(task_row)

        # 依存関係を取得（複合キー対応）
        if include_dependencies:
            deps = fetch_all(
                conn,
                """
                SELECT
                    td.depends_on_task_id,
                    t.title as dependency_title,
                    t.status as dependency_status
                FROM task_dependencies td
                JOIN tasks t ON td.depends_on_task_id = t.id AND td.project_id = t.project_id
                WHERE td.task_id = ? AND td.project_id = ?
                """,
                (task_id, project_id)
            )
            task["depends_on"] = [
                {
                    "task_id": d["depends_on_task_id"],
                    "title": d["dependency_title"],
                    "status": d["dependency_status"]
                }
                for d in deps
            ]

            # このタスクに依存しているタスク（逆依存）（複合キー対応）
            dependents = fetch_all(
                conn,
                """
                SELECT
                    td.task_id as dependent_task_id,
                    t.title as dependent_title,
                    t.status as dependent_status
                FROM task_dependencies td
                JOIN tasks t ON td.task_id = t.id AND td.project_id = t.project_id
                WHERE td.depends_on_task_id = ? AND td.project_id = ?
                """,
                (task_id, project_id)
            )
            task["dependents"] = [
                {
                    "task_id": d["dependent_task_id"],
                    "title": d["dependent_title"],
                    "status": d["dependent_status"]
                }
                for d in dependents
            ]

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
                WHERE entity_type = 'task' AND entity_id = ?
                ORDER BY changed_at DESC
                LIMIT 20
                """,
                (task_id,)
            )
            task["history"] = rows_to_dicts(history)

        return task

    finally:
        conn.close()


def format_detail(task: Dict[str, Any]) -> str:
    """
    タスク詳細を読みやすい形式でフォーマット
    """
    lines = [
        f"# {task['id']}: {task['title']}",
        "",
        "## 基本情報",
        f"- **ORDER**: {task['order_id']} ({task.get('order_title', '')})",
        f"- **ステータス**: {task['status']}",
        f"- **担当者**: {task.get('assignee') or '-'}",
        f"- **優先度**: {task['priority']}",
        f"- **推奨モデル**: {task.get('recommended_model') or '-'}",
        "",
    ]

    if task.get("description"):
        lines.extend([
            "## 説明",
            task["description"],
            "",
        ])

    # 依存関係
    if task.get("depends_on"):
        lines.append("## 依存タスク（このタスクが依存しているタスク）")
        for dep in task["depends_on"]:
            lines.append(f"- {dep['task_id']}: {dep['title']} ({dep['status']})")
        lines.append("")

    if task.get("dependents"):
        lines.append("## 被依存タスク（このタスクに依存しているタスク）")
        for dep in task["dependents"]:
            lines.append(f"- {dep['task_id']}: {dep['title']} ({dep['status']})")
        lines.append("")

    # タイムスタンプ
    lines.extend([
        "## タイムスタンプ",
        f"- **作成日時**: {task['created_at']}",
        f"- **更新日時**: {task['updated_at']}",
        f"- **開始日時**: {task.get('started_at') or '-'}",
        f"- **完了日時**: {task.get('completed_at') or '-'}",
        "",
    ])

    # 変更履歴
    if task.get("history"):
        lines.append("## 変更履歴（最新20件）")
        for h in task["history"]:
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
        description="タスク詳細を取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("task_id", help="タスクID")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    parser.add_argument("--detail", action="store_true", help="詳細情報を含める")
    parser.add_argument("--no-deps", action="store_true", help="依存関係を含めない")

    args = parser.parse_args()

    try:
        task = get_task(
            args.project_id,
            args.task_id,
            include_dependencies=not args.no_deps,
            include_history=args.detail,
        )

        if not task:
            print(f"エラー: タスクが見つかりません: {args.task_id}", file=sys.stderr)
            sys.exit(1)

        if args.json:
            print(json.dumps(task, ensure_ascii=False, indent=2, default=str))
        else:
            print(format_detail(task))

    except (ValidationError, DatabaseError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
