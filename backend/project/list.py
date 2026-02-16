#!/usr/bin/env python3
"""
AI PM Framework - プロジェクト一覧取得スクリプト

Usage:
    python backend/project/list.py [options]

Options:
    --status        ステータスでフィルタ（カンマ区切りで複数指定可）
    --active        アクティブなプロジェクトのみ（PLANNING/IN_PROGRESS/REVIEW/REWORK）
    --completed     完了済みプロジェクトのみ（COMPLETED）
    --on-hold       一時停止中のプロジェクトのみ（ON_HOLD）
    --all           全プロジェクト表示（アクティブ・非アクティブ両方）
    --inactive      非アクティブプロジェクトのみ表示
    --limit         取得件数制限
    --summary       サマリのみ表示
    --json          JSON形式で出力（デフォルト）
    --table         テーブル形式で出力

Example:
    python backend/project/list.py              # アクティブプロジェクトのみ（デフォルト）
    python backend/project/list.py --all        # 全プロジェクト
    python backend/project/list.py --inactive   # 非アクティブプロジェクトのみ
    python backend/project/list.py --active     # ステータスがアクティブなプロジェクトのみ
    python backend/project/list.py --status IN_PROGRESS,REVIEW --table
    python backend/project/list.py --summary
"""

import argparse
import json
import sys
from dataclasses import dataclass, asdict
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
from utils.validation import ValidationError


# プロジェクトステータスの有効値
VALID_PROJECT_STATUSES = (
    'INITIAL', 'PLANNING', 'IN_PROGRESS', 'REVIEW', 'REWORK',
    'ESCALATED', 'ESCALATION_RESOLVED', 'COMPLETED', 'ON_HOLD',
    'CANCELLED', 'INTERRUPTED'
)

# アクティブステータス
ACTIVE_STATUSES = ('PLANNING', 'IN_PROGRESS', 'REVIEW', 'REWORK', 'ESCALATED', 'ESCALATION_RESOLVED')


def validate_project_status(status: str) -> None:
    """プロジェクトステータスを検証"""
    if status not in VALID_PROJECT_STATUSES:
        raise ValidationError(
            f"無効なプロジェクトステータス: {status}. "
            f"有効な値: {', '.join(VALID_PROJECT_STATUSES)}"
        )


@dataclass
class ProjectSummary:
    """プロジェクト集計サマリ"""
    total_count: int = 0
    active_count: int = 0
    completed_count: int = 0
    on_hold_count: int = 0
    cancelled_count: int = 0
    active_projects: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.active_projects is None:
            self.active_projects = []


def _check_is_active_column_exists(conn) -> bool:
    """
    is_active カラムが存在するかチェック（後方互換性用）

    Args:
        conn: データベース接続

    Returns:
        is_active カラムが存在する場合は True
    """
    try:
        result = fetch_all(
            conn,
            "PRAGMA table_info(projects)"
        )
        column_names = [row["name"] for row in result]
        return "is_active" in column_names
    except Exception:
        return False


def list_projects(
    *,
    status: Optional[List[str]] = None,
    active_only: bool = False,
    completed_only: bool = False,
    on_hold_only: bool = False,
    limit: Optional[int] = None,
    include_order_count: bool = True,
    include_task_stats: bool = True,
    is_active: Optional[bool] = None,
    include_inactive: bool = False,
) -> List[Dict[str, Any]]:
    """
    プロジェクト一覧を取得

    Args:
        status: ステータスでフィルタ（リスト）
        active_only: アクティブなプロジェクトのみ（プロジェクトステータス基準）
        completed_only: 完了済みプロジェクトのみ
        on_hold_only: 一時停止中プロジェクトのみ
        limit: 取得件数制限
        include_order_count: ORDER数を含めるか
        include_task_stats: タスク統計を含めるか
        is_active: is_activeフラグでフィルタ（True=アクティブのみ, False=非アクティブのみ, None=全て）
        include_inactive: is_active=True/Falseの両方を含める（is_active=Noneと同等だが明示的）

    Returns:
        プロジェクトのリスト

    Raises:
        ValidationError: 入力検証エラー
        DatabaseError: DB操作エラー

    Note:
        デフォルトでは is_active が指定されない場合、アクティブプロジェクトのみを返します。
        全プロジェクトを取得するには is_active=None かつ include_inactive=True を指定してください。
    """
    # ステータス検証
    if status:
        for s in status:
            validate_project_status(s)

    conn = get_connection()
    try:
        # is_active カラムの存在チェック（後方互換性）
        has_is_active_column = _check_is_active_column_exists(conn)

        # クエリ構築
        if has_is_active_column:
            query = """
            SELECT
                p.id,
                p.name,
                p.path,
                p.status,
                p.current_order_id,
                p.created_at,
                p.updated_at,
                p.is_active
            FROM projects p
            WHERE 1=1
            """
        else:
            query = """
            SELECT
                p.id,
                p.name,
                p.path,
                p.status,
                p.current_order_id,
                p.created_at,
                p.updated_at
            FROM projects p
            WHERE 1=1
            """
        params: List[Any] = []

        # is_active フィルタ（カラムが存在する場合のみ）
        if has_is_active_column:
            if include_inactive:
                # --all の場合: is_active でフィルタしない（全て表示）
                # ただし、is_active が明示的に指定されている場合はそれを優先
                if is_active is True:
                    query += " AND p.is_active = 1"
                elif is_active is False:
                    query += " AND p.is_active = 0"
                # is_active=None かつ include_inactive=True: フィルタなし
            else:
                if is_active is True:
                    query += " AND p.is_active = 1"
                elif is_active is False:
                    query += " AND p.is_active = 0"
                elif is_active is None:
                    # デフォルト動作: アクティブプロジェクトのみ
                    query += " AND p.is_active = 1"

        # ステータスフィルタ
        if status:
            placeholders = ", ".join(["?" for _ in status])
            query += f" AND p.status IN ({placeholders})"
            params.extend(status)
        elif active_only:
            placeholders = ", ".join(["?" for _ in ACTIVE_STATUSES])
            query += f" AND p.status IN ({placeholders})"
            params.extend(ACTIVE_STATUSES)
        elif completed_only:
            query += " AND p.status = 'COMPLETED'"
        elif on_hold_only:
            query += " AND p.status = 'ON_HOLD'"

        # ソート（ステータス順、更新日順）
        query += """
        ORDER BY
            CASE p.status
                WHEN 'IN_PROGRESS' THEN 0
                WHEN 'REVIEW' THEN 1
                WHEN 'REWORK' THEN 2
                WHEN 'PLANNING' THEN 3
                WHEN 'ESCALATED' THEN 4
                WHEN 'ESCALATION_RESOLVED' THEN 5
                WHEN 'ON_HOLD' THEN 6
                WHEN 'INITIAL' THEN 7
                WHEN 'COMPLETED' THEN 8
                WHEN 'CANCELLED' THEN 9
                WHEN 'INTERRUPTED' THEN 10
            END,
            p.updated_at DESC
        """

        # 件数制限
        if limit:
            query += " LIMIT ?"
            params.append(limit)

        rows = fetch_all(conn, query, tuple(params) if params else None)
        projects = rows_to_dicts(rows)

        # is_active カラムがない場合、デフォルト値を追加（後方互換性）
        if not has_is_active_column:
            for project in projects:
                project["is_active"] = True

        # ORDER数を追加
        if include_order_count:
            for project in projects:
                # ORDER総数
                order_count = fetch_one(
                    conn,
                    "SELECT COUNT(*) as count FROM orders WHERE project_id = ?",
                    (project["id"],)
                )
                project["order_count"] = order_count["count"] if order_count else 0

                # アクティブORDER数
                active_order_count = fetch_one(
                    conn,
                    """
                    SELECT COUNT(*) as count FROM orders
                    WHERE project_id = ? AND status IN ('PLANNING', 'IN_PROGRESS', 'REVIEW')
                    """,
                    (project["id"],)
                )
                project["active_order_count"] = active_order_count["count"] if active_order_count else 0

                # 完了ORDER数
                completed_order_count = fetch_one(
                    conn,
                    """
                    SELECT COUNT(*) as count FROM orders
                    WHERE project_id = ? AND status = 'COMPLETED'
                    """,
                    (project["id"],)
                )
                project["completed_order_count"] = completed_order_count["count"] if completed_order_count else 0

        # タスク統計を追加
        if include_task_stats:
            for project in projects:
                # タスク総数
                task_count = fetch_one(
                    conn,
                    "SELECT COUNT(*) as count FROM tasks WHERE project_id = ?",
                    (project["id"],)
                )
                project["task_count"] = task_count["count"] if task_count else 0

                # 完了タスク数
                completed_task_count = fetch_one(
                    conn,
                    "SELECT COUNT(*) as count FROM tasks WHERE project_id = ? AND status = 'COMPLETED'",
                    (project["id"],)
                )
                project["completed_task_count"] = completed_task_count["count"] if completed_task_count else 0

                # 実行中タスク数
                in_progress_count = fetch_one(
                    conn,
                    "SELECT COUNT(*) as count FROM tasks WHERE project_id = ? AND status = 'IN_PROGRESS'",
                    (project["id"],)
                )
                project["in_progress_task_count"] = in_progress_count["count"] if in_progress_count else 0

                # タスク進捗率
                if project["task_count"] > 0:
                    project["task_progress_percent"] = round(
                        (project["completed_task_count"] / project["task_count"]) * 100
                    )
                else:
                    project["task_progress_percent"] = 0

        return projects

    finally:
        conn.close()


def list_active_projects(**kwargs) -> List[Dict[str, Any]]:
    """
    アクティブなプロジェクトのみを取得（ショートカット関数）

    is_active=True のプロジェクトのみ返します。
    その他のオプションは list_projects に渡されます。
    """
    return list_projects(is_active=True, **kwargs)


def list_inactive_projects(**kwargs) -> List[Dict[str, Any]]:
    """
    非アクティブなプロジェクトのみを取得（ショートカット関数）

    is_active=False のプロジェクトのみ返します。
    その他のオプションは list_projects に渡されます。
    """
    return list_projects(is_active=False, include_inactive=True, **kwargs)


def list_all_projects(**kwargs) -> List[Dict[str, Any]]:
    """
    全プロジェクトを取得（ショートカット関数）

    is_active フラグに関係なく全プロジェクトを返します。
    その他のオプションは list_projects に渡されます。
    """
    return list_projects(include_inactive=True, **kwargs)


def get_project_summary() -> ProjectSummary:
    """
    プロジェクト集計サマリを取得

    Returns:
        ProjectSummary: 集計サマリ

    Raises:
        DatabaseError: DB操作エラー
    """
    conn = get_connection()
    try:
        # ステータス別件数
        count_query = """
        SELECT status, COUNT(*) as count
        FROM projects
        GROUP BY status
        """
        rows = fetch_all(conn, count_query)

        summary = ProjectSummary()

        for row in rows:
            status = row["status"]
            count = row["count"]
            summary.total_count += count

            if status in ACTIVE_STATUSES:
                summary.active_count += count
            elif status == "COMPLETED":
                summary.completed_count += count
            elif status == "ON_HOLD":
                summary.on_hold_count += count
            elif status == "CANCELLED":
                summary.cancelled_count += count

        # アクティブプロジェクトの詳細
        active_projects = list_projects(
            active_only=True,
            include_order_count=True,
            include_task_stats=True,
        )
        summary.active_projects = active_projects

        return summary

    finally:
        conn.close()


def format_table(projects: List[Dict[str, Any]], include_active_flag: bool = False) -> str:
    """
    プロジェクトリストをテーブル形式でフォーマット

    Args:
        projects: プロジェクトのリスト
        include_active_flag: is_active フラグをテーブルに含めるか
    """
    if not projects:
        return "プロジェクトが見つかりません。"

    # ヘッダー
    if include_active_flag:
        lines = [
            "| ID | 名前 | Active | ステータス | ORDER数 | タスク進捗 | 現在ORDER |",
            "|----|------|--------|------------|---------|------------|-----------|"
        ]
    else:
        lines = [
            "| ID | 名前 | ステータス | ORDER数 | タスク進捗 | 現在ORDER |",
            "|----|------|------------|---------|------------|-----------|"
        ]

    for p in projects:
        task_progress = f"{p.get('task_progress_percent', 0)}%"
        if p.get('task_count', 0) > 0:
            task_progress += f" ({p.get('completed_task_count', 0)}/{p.get('task_count', 0)})"

        order_info = f"{p.get('active_order_count', 0)}/{p.get('order_count', 0)}"

        current_order = p.get('current_order_id') or "-"

        # is_active フラグの表示
        active_flag = "✓" if p.get('is_active', True) else "-"

        if include_active_flag:
            lines.append(
                f"| {p['id']} | {p['name'][:15]} | {active_flag} | {p['status']} | {order_info} | {task_progress} | {current_order} |"
            )
        else:
            lines.append(
                f"| {p['id']} | {p['name'][:15]} | {p['status']} | {order_info} | {task_progress} | {current_order} |"
            )

    return "\n".join(lines)


def format_summary(summary: ProjectSummary) -> str:
    """
    サマリをフォーマット
    """
    lines = [
        "プロジェクト集計サマリ",
        "-" * 40,
        f"  合計: {summary.total_count}件",
        f"  アクティブ: {summary.active_count}件",
        f"  完了済み: {summary.completed_count}件",
        f"  一時停止: {summary.on_hold_count}件",
        f"  キャンセル: {summary.cancelled_count}件",
    ]

    if summary.active_projects:
        lines.append("\nアクティブプロジェクト:")
        for p in summary.active_projects:
            task_progress = f"{p.get('task_progress_percent', 0)}%"
            current_order = p.get('current_order_id') or "-"
            lines.append(f"  - {p['id']}: {p['name'][:25]} ({p['status']}, {task_progress}, 現在: {current_order})")

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
        description="プロジェクト一覧を取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("--status", help="ステータスでフィルタ（カンマ区切り）")
    parser.add_argument("--active", action="store_true", help="アクティブなプロジェクトのみ（ステータス基準）")
    parser.add_argument("--completed", action="store_true", help="完了済みプロジェクトのみ")
    parser.add_argument("--on-hold", action="store_true", help="一時停止中プロジェクトのみ")
    parser.add_argument("--limit", type=int, help="取得件数制限")
    parser.add_argument("--summary", action="store_true", help="サマリのみ表示")
    parser.add_argument("--table", action="store_true", help="テーブル形式で出力")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    # is_active フィルタリングオプション
    parser.add_argument("--all", dest="include_all", action="store_true",
                        help="全プロジェクト表示（アクティブ・非アクティブ両方）")
    parser.add_argument("--inactive", action="store_true",
                        help="非アクティブプロジェクトのみ表示")

    args = parser.parse_args()

    # ステータスのパース
    status_list = None
    if args.status:
        status_list = [s.strip() for s in args.status.split(",") if s.strip()]

    try:
        # is_active フィルタリングオプションの処理
        is_active_filter = None
        include_inactive = False

        if args.include_all:
            # --all: 全プロジェクト表示
            include_inactive = True
        elif args.inactive:
            # --inactive: 非アクティブのみ
            is_active_filter = False
            include_inactive = True
        else:
            # デフォルト: アクティブのみ
            is_active_filter = True

        if args.summary:
            summary = get_project_summary()
            if args.json:
                output = asdict(summary)
                print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
            else:
                print(format_summary(summary))
        else:
            projects = list_projects(
                status=status_list,
                active_only=args.active,
                completed_only=args.completed,
                on_hold_only=args.on_hold,
                limit=args.limit,
                is_active=is_active_filter,
                include_inactive=include_inactive,
            )

            # --all または --inactive の場合、テーブルに is_active フラグを表示
            show_active_flag = args.include_all or args.inactive

            if args.table:
                print(format_table(projects, include_active_flag=show_active_flag))
            else:
                # デフォルトはJSON
                print(json.dumps(projects, ensure_ascii=False, indent=2, default=str))

    except (ValidationError, DatabaseError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
