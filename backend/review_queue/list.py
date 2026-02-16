"""
AI PM Framework - レビューキュー一覧取得スクリプト

レビューキューの一覧を優先度順にソートして取得。
"""

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import (
    get_connection,
    fetch_all,
    fetch_one,
    rows_to_dicts,
    DatabaseError,
)


@dataclass
class QueueItem:
    """レビューキューアイテム"""
    queue_id: int
    task_id: str
    task_title: str
    task_status: str
    order_id: str
    order_title: str
    project_id: str
    project_name: str
    submitted_at: str
    review_status: str
    reviewer: Optional[str]
    priority: str
    comment: Optional[str]
    reviewed_at: Optional[str]
    assignee: Optional[str]


def list_queue(
    project_name: str,
    order_id: Optional[str] = None,
    status_filter: Optional[List[str]] = None,
    include_completed: bool = False,
    db_path: Optional[Path] = None,
) -> List[QueueItem]:
    """
    レビューキュー一覧を取得

    Args:
        project_name: プロジェクト名
        order_id: ORDER ID でフィルタ（オプション）
        status_filter: レビューステータスでフィルタ（オプション）
        include_completed: 完了済み（APPROVED）を含めるか
        db_path: データベースパス（テスト用）

    Returns:
        List[QueueItem]: レビューキューアイテムのリスト（優先度順）

    Sort Order:
        1. 優先度: P0 > P1 > P2
        2. 提出日時: 古い順（FIFO）
    """
    try:
        conn = get_connection(db_path)
        try:
            # 基本クエリ（複合キー対応）
            query = """
            SELECT
                rq.id as queue_id,
                rq.task_id,
                t.title as task_title,
                t.status as task_status,
                t.assignee,
                t.order_id as order_id,
                o.title as order_title,
                rq.project_id as project_id,
                p.name as project_name,
                rq.submitted_at,
                rq.status as review_status,
                rq.reviewer,
                rq.priority,
                rq.comment,
                rq.reviewed_at
            FROM review_queue rq
            JOIN tasks t ON rq.task_id = t.id AND rq.project_id = t.project_id
            JOIN orders o ON t.order_id = o.id AND t.project_id = o.project_id
            JOIN projects p ON rq.project_id = p.id
            WHERE rq.project_id = ?
            """

            params = [project_name]

            # ORDER IDフィルタ
            if order_id:
                query += " AND o.id = ?"
                params.append(order_id)

            # ステータスフィルタ
            if status_filter:
                placeholders = ", ".join(["?" for _ in status_filter])
                query += f" AND rq.status IN ({placeholders})"
                params.extend(status_filter)
            elif not include_completed:
                # デフォルトでは APPROVED を除外
                query += " AND rq.status IN ('PENDING', 'IN_REVIEW', 'REJECTED')"

            # ソート: 優先度 → 提出日時
            query += """
            ORDER BY
                CASE rq.priority
                    WHEN 'P0' THEN 0
                    WHEN 'P1' THEN 1
                    WHEN 'P2' THEN 2
                END,
                rq.submitted_at
            """

            rows = fetch_all(conn, query, tuple(params))

            return [
                QueueItem(
                    queue_id=row["queue_id"],
                    task_id=row["task_id"],
                    task_title=row["task_title"],
                    task_status=row["task_status"],
                    order_id=row["order_id"],
                    order_title=row["order_title"],
                    project_id=row["project_id"],
                    project_name=row["project_name"],
                    submitted_at=row["submitted_at"],
                    review_status=row["review_status"],
                    reviewer=row["reviewer"],
                    priority=row["priority"],
                    comment=row["comment"],
                    reviewed_at=row["reviewed_at"],
                    assignee=row["assignee"],
                )
                for row in rows
            ]

        finally:
            conn.close()

    except DatabaseError as e:
        print(f"データベースエラー: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        return []


def get_queue_summary(
    project_name: str,
    db_path: Optional[Path] = None,
) -> dict:
    """
    レビューキューのサマリを取得

    Args:
        project_name: プロジェクト名
        db_path: データベースパス

    Returns:
        dict: サマリ情報
            - pending_count: PENDING件数
            - in_review_count: IN_REVIEW件数
            - rejected_count: REJECTED件数（要再提出）
            - p0_count: P0（高優先）件数
            - oldest_pending: 最古のPENDINGタスク
    """
    try:
        conn = get_connection(db_path)
        try:
            # 各ステータスの件数を取得（複合キー対応）
            count_query = """
            SELECT
                rq.status,
                rq.priority,
                COUNT(*) as count
            FROM review_queue rq
            WHERE rq.project_id = ?
              AND rq.status IN ('PENDING', 'IN_REVIEW', 'REJECTED')
            GROUP BY rq.status, rq.priority
            """

            rows = fetch_all(conn, count_query, (project_name,))

            summary = {
                "pending_count": 0,
                "in_review_count": 0,
                "rejected_count": 0,
                "p0_count": 0,
                "total_active": 0,
            }

            for row in rows:
                status = row["status"]
                priority = row["priority"]
                count = row["count"]

                if status == "PENDING":
                    summary["pending_count"] += count
                elif status == "IN_REVIEW":
                    summary["in_review_count"] += count
                elif status == "REJECTED":
                    summary["rejected_count"] += count

                if priority == "P0":
                    summary["p0_count"] += count

                summary["total_active"] += count

            # 最古のPENDINGタスクを取得（複合キー対応）
            oldest_query = """
            SELECT rq.task_id, rq.submitted_at, rq.priority
            FROM review_queue rq
            WHERE rq.project_id = ?
              AND rq.status = 'PENDING'
            ORDER BY
                CASE rq.priority
                    WHEN 'P0' THEN 0
                    WHEN 'P1' THEN 1
                    WHEN 'P2' THEN 2
                END,
                rq.submitted_at
            LIMIT 1
            """

            oldest = fetch_one(conn, oldest_query, (project_name,))
            if oldest:
                summary["next_task"] = {
                    "task_id": oldest["task_id"],
                    "submitted_at": oldest["submitted_at"],
                    "priority": oldest["priority"],
                }
            else:
                summary["next_task"] = None

            return summary

        finally:
            conn.close()

    except Exception as e:
        return {"error": str(e)}


def format_table(items: List[QueueItem]) -> str:
    """
    レビューキューをテーブル形式でフォーマット

    Args:
        items: レビューキューアイテムのリスト

    Returns:
        str: テーブル形式の文字列
    """
    if not items:
        return "レビューキューは空です"

    # ヘッダー
    lines = [
        "| Task ID | タスク名 | 優先度 | ステータス | 提出日時 | レビュアー | 備考 |",
        "|---------|---------|--------|----------|---------|-----------|------|"
    ]

    for item in items:
        submitted = item.submitted_at[:16] if item.submitted_at else "-"
        reviewer = item.reviewer or "-"
        comment = item.comment[:20] + "..." if item.comment and len(item.comment) > 20 else (item.comment or "-")

        lines.append(
            f"| {item.task_id} | {item.task_title[:20]} | {item.priority} | "
            f"{item.review_status} | {submitted} | {reviewer} | {comment} |"
        )

    return "\n".join(lines)


def main():
    """コマンドライン実行"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from config import setup_utf8_output
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="レビューキュー一覧を取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # プロジェクトのレビューキュー一覧
  python list.py AI_PM_PJ

  # 特定ORDERのレビューキュー
  python list.py AI_PM_PJ --order ORDER_036

  # PENDINGのみ表示
  python list.py AI_PM_PJ --status PENDING

  # JSON形式で出力
  python list.py AI_PM_PJ --json

  # サマリのみ表示
  python list.py AI_PM_PJ --summary
"""
    )

    parser.add_argument(
        "project_name",
        help="プロジェクト名 (例: AI_PM_PJ)"
    )
    parser.add_argument(
        "--order", "-o",
        help="ORDER ID でフィルタ (例: ORDER_036)"
    )
    parser.add_argument(
        "--status", "-s",
        nargs="+",
        choices=["PENDING", "IN_REVIEW", "REJECTED", "APPROVED"],
        help="レビューステータスでフィルタ"
    )
    parser.add_argument(
        "--include-completed",
        action="store_true",
        help="完了済み（APPROVED）を含める"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="サマリのみ表示"
    )

    args = parser.parse_args()

    if args.summary:
        summary = get_queue_summary(args.project_name)
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(f"レビューキューサマリ ({args.project_name})")
            print("-" * 40)
            print(f"  PENDING: {summary.get('pending_count', 0)}件")
            print(f"  IN_REVIEW: {summary.get('in_review_count', 0)}件")
            print(f"  REJECTED: {summary.get('rejected_count', 0)}件")
            print(f"  高優先(P0): {summary.get('p0_count', 0)}件")
            print(f"  合計: {summary.get('total_active', 0)}件")
            if summary.get("next_task"):
                next_task = summary["next_task"]
                print(f"\n次のレビュー対象: {next_task['task_id']} (優先度: {next_task['priority']})")
    else:
        items = list_queue(
            project_name=args.project_name,
            order_id=args.order,
            status_filter=args.status,
            include_completed=args.include_completed,
        )

        if args.json:
            output = [asdict(item) for item in items]
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            print(f"レビューキュー一覧 ({args.project_name})")
            if args.order:
                print(f"  フィルタ: {args.order}")
            print()
            print(format_table(items))
            print(f"\n合計: {len(items)}件")


if __name__ == "__main__":
    main()
