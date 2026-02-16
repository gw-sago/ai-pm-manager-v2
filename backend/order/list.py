#!/usr/bin/env python3
"""
AI PM Framework - ORDER一覧取得スクリプト

Usage:
    python backend/order/list.py PROJECT_NAME [options]

Options:
    --status        ステータスでフィルタ（カンマ区切りで複数指定可）
    --priority      優先度でフィルタ
    --active        アクティブなORDERのみ（PLANNING/IN_PROGRESS/REVIEW）
    --completed     完了済みORDERのみ（COMPLETED）
    --on-hold       一時停止中のORDERのみ（ON_HOLD）
    --limit         取得件数制限
    --summary       サマリのみ表示
    --json          JSON形式で出力（デフォルト）
    --table         テーブル形式で出力

Example:
    python backend/order/list.py AI_PM_PJ
    python backend/order/list.py AI_PM_PJ --active
    python backend/order/list.py AI_PM_PJ --status IN_PROGRESS,REVIEW --table
    python backend/order/list.py AI_PM_PJ --summary
"""

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
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
from utils.validation import (
    validate_project_name, validate_status, project_exists, ValidationError
)


@dataclass
class OrderSummary:
    """ORDER集計サマリ"""
    total_count: int = 0
    active_count: int = 0
    completed_count: int = 0
    on_hold_count: int = 0
    cancelled_count: int = 0
    active_orders: List[Dict[str, Any]] = None
    recommended_max_active: int = 3
    hard_max_active: int = 5

    def __post_init__(self):
        if self.active_orders is None:
            self.active_orders = []


def list_orders(
    project_id: str,
    *,
    status: Optional[List[str]] = None,
    priority: Optional[str] = None,
    active_only: bool = False,
    completed_only: bool = False,
    on_hold_only: bool = False,
    limit: Optional[int] = None,
    include_task_count: bool = True,
) -> List[Dict[str, Any]]:
    """
    ORDER一覧を取得

    Args:
        project_id: プロジェクトID
        status: ステータスでフィルタ（リスト）
        priority: 優先度でフィルタ
        active_only: アクティブなORDERのみ
        completed_only: 完了済みORDERのみ
        on_hold_only: 一時停止中ORDERのみ
        limit: 取得件数制限
        include_task_count: タスク数を含めるか

    Returns:
        ORDERのリスト

    Raises:
        ValidationError: 入力検証エラー
        DatabaseError: DB操作エラー
    """
    # 入力検証
    validate_project_name(project_id)

    if status:
        for s in status:
            validate_status(s, "order")

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
    WHERE o.project_id = ?
    """
    params: List[Any] = [project_id]

    # ステータスフィルタ
    if status:
        placeholders = ", ".join(["?" for _ in status])
        query += f" AND o.status IN ({placeholders})"
        params.extend(status)
    elif active_only:
        query += " AND o.status IN ('PLANNING', 'IN_PROGRESS', 'REVIEW')"
    elif completed_only:
        query += " AND o.status = 'COMPLETED'"
    elif on_hold_only:
        query += " AND o.status = 'ON_HOLD'"

    # 優先度フィルタ
    if priority:
        query += " AND o.priority = ?"
        params.append(priority)

    # ソート（優先度順、ステータス順、作成日順）
    query += """
    ORDER BY
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
        rows = fetch_all(conn, query, tuple(params))
        orders = rows_to_dicts(rows)

        # タスク数を追加（複合キー対応）
        if include_task_count:
            for order in orders:
                # タスク総数（複合キー対応）
                task_count = fetch_one(
                    conn,
                    "SELECT COUNT(*) as count FROM tasks WHERE order_id = ? AND project_id = ?",
                    (order["id"], project_id)
                )
                order["task_count"] = task_count["count"] if task_count else 0

                # 完了タスク数（複合キー対応）
                completed_count = fetch_one(
                    conn,
                    "SELECT COUNT(*) as count FROM tasks WHERE order_id = ? AND project_id = ? AND status = 'COMPLETED'",
                    (order["id"], project_id)
                )
                order["completed_task_count"] = completed_count["count"] if completed_count else 0

                # 進捗率
                if order["task_count"] > 0:
                    order["progress_percent"] = round(
                        (order["completed_task_count"] / order["task_count"]) * 100
                    )
                else:
                    order["progress_percent"] = 0

                # 実行中タスク（複合キー対応）
                in_progress = fetch_one(
                    conn,
                    """
                    SELECT t.id, t.title, t.assignee
                    FROM tasks t
                    WHERE t.order_id = ? AND t.project_id = ? AND t.status = 'IN_PROGRESS'
                    LIMIT 1
                    """,
                    (order["id"], project_id)
                )
                if in_progress:
                    order["in_progress_task"] = dict(in_progress)
                else:
                    order["in_progress_task"] = None

        return orders

    finally:
        conn.close()


def get_order_summary(
    project_id: str,
) -> OrderSummary:
    """
    ORDER集計サマリを取得

    Args:
        project_id: プロジェクトID

    Returns:
        OrderSummary: 集計サマリ

    Raises:
        ValidationError: 入力検証エラー
        DatabaseError: DB操作エラー
    """
    validate_project_name(project_id)

    conn = get_connection()
    try:
        # ステータス別件数
        count_query = """
        SELECT status, COUNT(*) as count
        FROM orders
        WHERE project_id = ?
        GROUP BY status
        """
        rows = fetch_all(conn, count_query, (project_id,))

        summary = OrderSummary()

        for row in rows:
            status = row["status"]
            count = row["count"]
            summary.total_count += count

            if status in ("PLANNING", "IN_PROGRESS", "REVIEW"):
                summary.active_count += count
            elif status == "COMPLETED":
                summary.completed_count += count
            elif status == "ON_HOLD":
                summary.on_hold_count += count
            elif status == "CANCELLED":
                summary.cancelled_count += count

        # アクティブORDERの詳細
        active_orders = list_orders(
            project_id,
            active_only=True,
            include_task_count=True,
        )
        summary.active_orders = active_orders

        return summary

    finally:
        conn.close()


def format_table(orders: List[Dict[str, Any]]) -> str:
    """
    ORDERリストをテーブル形式でフォーマット
    """
    if not orders:
        return "ORDERが見つかりません。"

    # ヘッダー
    lines = [
        "| ORDER ID | タイトル | ステータス | 優先度 | 進捗 | 担当Worker |",
        "|----------|----------|------------|--------|------|-----------|"
    ]

    for o in orders:
        progress = f"{o.get('progress_percent', 0)}%"
        if o.get('task_count', 0) > 0:
            progress += f" ({o.get('completed_task_count', 0)}/{o.get('task_count', 0)})"

        in_progress_task = o.get('in_progress_task')
        assignee = in_progress_task.get('assignee', '-') if in_progress_task else "-"

        lines.append(
            f"| {o['id']} | {o['title'][:20]} | {o['status']} | {o['priority']} | {progress} | {assignee} |"
        )

    return "\n".join(lines)


def format_summary(summary: OrderSummary) -> str:
    """
    サマリをフォーマット
    """
    lines = [
        f"ORDER集計サマリ",
        "-" * 40,
        f"  合計: {summary.total_count}件",
        f"  アクティブ: {summary.active_count}件 / {summary.recommended_max_active}件（推奨上限）",
        f"  完了済み: {summary.completed_count}件",
        f"  一時停止: {summary.on_hold_count}件",
        f"  キャンセル: {summary.cancelled_count}件",
    ]

    if summary.active_count >= summary.recommended_max_active:
        lines.append(f"\n【警告】アクティブORDERが推奨上限に達しています")

    if summary.active_orders:
        lines.append("\nアクティブORDER:")
        for o in summary.active_orders:
            progress = f"{o.get('progress_percent', 0)}%"
            lines.append(f"  - {o['id']}: {o['title'][:30]} ({o['status']}, {progress})")

    return "\n".join(lines)


def main():
    """CLI エントリーポイント"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
    except ImportError:
        from config import setup_utf8_output
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="ORDER一覧を取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("--status", help="ステータスでフィルタ（カンマ区切り）")
    parser.add_argument("--priority", help="優先度でフィルタ")
    parser.add_argument("--active", action="store_true", help="アクティブなORDERのみ")
    parser.add_argument("--completed", action="store_true", help="完了済みORDERのみ")
    parser.add_argument("--on-hold", action="store_true", help="一時停止中ORDERのみ")
    parser.add_argument("--limit", type=int, help="取得件数制限")
    parser.add_argument("--summary", action="store_true", help="サマリのみ表示")
    parser.add_argument("--table", action="store_true", help="テーブル形式で出力")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    # ステータスのパース
    status_list = None
    if args.status:
        status_list = [s.strip() for s in args.status.split(",") if s.strip()]

    try:
        if args.summary:
            summary = get_order_summary(args.project_id)
            if args.json:
                output = asdict(summary)
                print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
            else:
                print(format_summary(summary))
        else:
            orders = list_orders(
                args.project_id,
                status=status_list,
                priority=args.priority,
                active_only=args.active,
                completed_only=args.completed,
                on_hold_only=args.on_hold,
                limit=args.limit,
            )

            if args.table:
                print(format_table(orders))
            else:
                # デフォルトはJSON
                print(json.dumps(orders, ensure_ascii=False, indent=2, default=str))

    except (ValidationError, DatabaseError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
