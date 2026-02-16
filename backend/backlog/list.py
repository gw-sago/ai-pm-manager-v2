#!/usr/bin/env python3
"""
AI PM Framework - BACKLOG一覧取得スクリプト

Usage:
    python backend/backlog/list.py PROJECT_NAME [options]

Options:
    --category      カテゴリでフィルタ（複数指定可）
    --status        ステータスでフィルタ（TODO/IN_PROGRESS/DONE/CANCELED/EXTERNAL）（複数指定可）
    --priority      優先度でフィルタ（High/Medium/Low）（複数指定可）
    --project       プロジェクトでフィルタ（全プロジェクト横断時に使用）
    --sort          ソート順（priority/created/updated/status）
    --order         ソート方向（asc/desc）デフォルト: desc
    --json          JSON形式で出力
    --verbose       詳細情報を表示
    --all           全プロジェクト横断で取得

Example:
    python backend/backlog/list.py AI_PM_PJ
    python backend/backlog/list.py AI_PM_PJ --status TODO IN_PROGRESS --priority High Medium
    python backend/backlog/list.py AI_PM_PJ --sort priority --order asc --json
    python backend/backlog/list.py --all --status TODO --priority High
"""

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import (
    get_connection,
    transaction,
    fetch_all,
    rows_to_dicts,
    DatabaseError,
)
from utils.validation import (
    validate_project_name,
    project_exists,
    ValidationError,
    VALID_STATUSES,
)


# 優先度定義
VALID_PRIORITIES = ["High", "Medium", "Low"]

# 優先度の並び順（ソート用）
PRIORITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}

# ステータスの並び順（ソート用）
STATUS_ORDER = {"TODO": 0, "IN_PROGRESS": 1, "DONE": 2, "CANCELED": 3, "EXTERNAL": 4}


@dataclass
class ListBacklogResult:
    """BACKLOG一覧取得結果"""
    success: bool
    items: List[Dict[str, Any]] = None
    total_count: int = 0
    filtered_count: int = 0
    message: str = ""
    error: Optional[str] = None
    # フィルタ情報（ダッシュボード表示用）
    applied_filters: Dict[str, Any] = None

    def __post_init__(self):
        if self.items is None:
            self.items = []
        if self.applied_filters is None:
            self.applied_filters = {}


def list_backlogs(
    project_name: Optional[str] = None,
    *,
    category_filter: Optional[List[str]] = None,
    status_filter: Optional[List[str]] = None,
    priority_filter: Optional[List[str]] = None,
    project_filter: Optional[str] = None,
    sort_by: str = "priority",
    sort_order: str = "desc",
    include_order_info: bool = True,
    all_projects: bool = False,
    db_path: Optional[Path] = None,
    # 後方互換性のため旧パラメータもサポート
    category: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
) -> ListBacklogResult:
    """
    BACKLOG一覧を取得

    Args:
        project_name: プロジェクト名（all_projects=Trueの場合は省略可）
        category_filter: カテゴリフィルタリスト（複数指定可）
        status_filter: ステータスフィルタリスト（複数指定可）
        priority_filter: 優先度フィルタリスト（複数指定可）
        project_filter: プロジェクトフィルタ（all_projects時のみ有効）
        sort_by: ソート順（priority/created_at/updated_at/status/sort_order）
        sort_order: ソート方向（asc/desc）
        include_order_info: ORDER情報を含めるか
        all_projects: 全プロジェクト横断で取得するか
        db_path: データベースパス（テスト用）
        category: 後方互換用（単一値）
        status: 後方互換用（単一値）
        priority: 後方互換用（単一値）

    Returns:
        ListBacklogResult: 一覧取得結果

    Output Format (JSON):
        {
            "success": true,
            "items": [
                {
                    "id": "BACKLOG_029",
                    "title": "タイトル",
                    "description": "説明",
                    "priority": "High",
                    "status": "IN_PROGRESS",
                    "related_order_id": "ORDER_036",
                    "order_title": "ORDER名",
                    "order_status": "IN_PROGRESS",
                    "created_at": "2026-01-21T...",
                    "completed_at": null
                }
            ],
            "total_count": 31,
            "filtered_count": 5,
            "applied_filters": {
                "priority": ["High"],
                "status": ["TODO", "IN_PROGRESS"],
                "sort_by": "priority",
                "sort_order": "desc"
            }
        }
    """
    # 後方互換性: 旧パラメータを新パラメータに変換
    if category and not category_filter:
        category_filter = [category]
    if status and not status_filter:
        status_filter = [status]
    if priority and not priority_filter:
        priority_filter = [priority]
    # フィルタ情報を記録
    applied_filters = {
        "priority": priority_filter,
        "status": status_filter,
        "category": category_filter,
        "project": project_filter,
        "sort_by": sort_by,
        "sort_order": sort_order,
    }

    try:
        # 入力検証
        if not all_projects:
            if not project_name:
                return ListBacklogResult(
                    success=False,
                    error="プロジェクト名を指定してください（または --all を使用）",
                    applied_filters=applied_filters
                )
            validate_project_name(project_name)

        # ステータスフィルタの検証
        if status_filter:
            for s in status_filter:
                if s not in VALID_STATUSES["backlog"]:
                    return ListBacklogResult(
                        success=False,
                        error=f"無効なステータス: {s}\n有効なステータス: {', '.join(VALID_STATUSES['backlog'])}",
                        applied_filters=applied_filters
                    )

        # 優先度フィルタの検証
        if priority_filter:
            for p in priority_filter:
                if p not in VALID_PRIORITIES:
                    return ListBacklogResult(
                        success=False,
                        error=f"無効な優先度: {p}\n有効な優先度: {', '.join(VALID_PRIORITIES)}",
                        applied_filters=applied_filters
                    )

        # ソート方向の検証
        if sort_order not in ["asc", "desc"]:
            return ListBacklogResult(
                success=False,
                error=f"無効なソート方向: {sort_order}\n有効な値: asc, desc",
                applied_filters=applied_filters
            )

        with transaction(db_path=db_path) as conn:
            # プロジェクト存在確認（単一プロジェクトモード時のみ）
            if not all_projects and not project_exists(conn, project_name):
                return ListBacklogResult(
                    success=False,
                    error=f"プロジェクトが見つかりません: {project_name}",
                    applied_filters=applied_filters
                )

            # SQLクエリ構築
            # 注: 同一プロジェクト内のORDERを優先してJOIN、なければ他プロジェクトのORDERも参照
            if include_order_info:
                base_query = """
                SELECT
                    b.id,
                    b.project_id,
                    b.title,
                    b.description,
                    b.priority,
                    b.status,
                    b.related_order_id,
                    b.sort_order,
                    b.created_at,
                    b.completed_at,
                    b.updated_at,
                    COALESCE(o_same.title, o_other.title) as order_title,
                    COALESCE(o_same.status, o_other.status) as order_status,
                    COALESCE(o_same.project_id, o_other.project_id) as order_project_id,
                    COALESCE(task_stats_same.total_tasks, task_stats_other.total_tasks, 0) as total_tasks,
                    COALESCE(task_stats_same.completed_tasks, task_stats_other.completed_tasks, 0) as completed_tasks,
                    CASE
                        WHEN COALESCE(task_stats_same.total_tasks, task_stats_other.total_tasks, 0) > 0
                        THEN ROUND(COALESCE(task_stats_same.completed_tasks, task_stats_other.completed_tasks, 0) * 100.0 /
                                   COALESCE(task_stats_same.total_tasks, task_stats_other.total_tasks, 1))
                        ELSE 0
                    END as progress_percent
                FROM backlog_items b
                -- 同一プロジェクト内のORDER (優先)
                LEFT JOIN orders o_same ON b.related_order_id = o_same.id AND b.project_id = o_same.project_id
                -- 別プロジェクトのORDER (フォールバック)
                LEFT JOIN orders o_other ON b.related_order_id = o_other.id AND o_same.id IS NULL
                -- タスク統計 (同一プロジェクト)
                LEFT JOIN (
                    SELECT
                        order_id,
                        project_id,
                        COUNT(*) as total_tasks,
                        SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed_tasks
                    FROM tasks
                    GROUP BY order_id, project_id
                ) task_stats_same ON o_same.id = task_stats_same.order_id AND o_same.project_id = task_stats_same.project_id
                -- タスク統計 (別プロジェクト)
                LEFT JOIN (
                    SELECT
                        order_id,
                        project_id,
                        COUNT(*) as total_tasks,
                        SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed_tasks
                    FROM tasks
                    GROUP BY order_id, project_id
                ) task_stats_other ON o_other.id = task_stats_other.order_id AND o_other.project_id = task_stats_other.project_id AND o_same.id IS NULL
                WHERE 1=1
                """
            else:
                base_query = """
                SELECT
                    b.id,
                    b.project_id,
                    b.title,
                    b.description,
                    b.priority,
                    b.status,
                    b.related_order_id,
                    b.sort_order,
                    b.created_at,
                    b.completed_at,
                    b.updated_at
                FROM backlog_items b
                WHERE 1=1
                """

            params: List[Any] = []

            # プロジェクトフィルタ
            if not all_projects:
                base_query += " AND b.project_id = ?"
                params.append(project_name)
            elif project_filter:
                base_query += " AND b.project_id = ?"
                params.append(project_filter)

            # ステータスフィルタ（複数値対応）
            if status_filter:
                placeholders = ",".join(["?" for _ in status_filter])
                base_query += f" AND b.status IN ({placeholders})"
                params.extend(status_filter)

            # 優先度フィルタ（複数値対応）
            if priority_filter:
                placeholders = ",".join(["?" for _ in priority_filter])
                base_query += f" AND b.priority IN ({placeholders})"
                params.extend(priority_filter)

            # カテゴリフィルタ（複数値対応、OR条件）
            if category_filter:
                category_conditions = []
                for cat in category_filter:
                    category_conditions.append("b.description LIKE ?")
                    params.append(f"%カテゴリ: {cat}%")
                base_query += f" AND ({' OR '.join(category_conditions)})"

            # ソート順の方向を決定
            order_direction = "ASC" if sort_order == "asc" else "DESC"
            reverse_direction = "DESC" if sort_order == "asc" else "ASC"

            # ソート順（sort_order対応）
            if sort_by == "priority":
                priority_case = """
                    CASE b.priority
                        WHEN 'High' THEN 0
                        WHEN 'Medium' THEN 1
                        WHEN 'Low' THEN 2
                    END"""
                status_case = """
                    CASE b.status
                        WHEN 'TODO' THEN 0
                        WHEN 'IN_PROGRESS' THEN 1
                        WHEN 'DONE' THEN 2
                        WHEN 'CANCELED' THEN 3
                        WHEN 'EXTERNAL' THEN 4
                    END"""
                base_query += f"""
                ORDER BY
                    {priority_case} {order_direction},
                    {status_case} {order_direction},
                    b.created_at {reverse_direction}
                """
            elif sort_by == "sort_order":
                # 数値優先度順（小さい方が高優先度）、999は末尾
                base_query += f" ORDER BY b.sort_order {order_direction}, b.created_at {reverse_direction}"
            elif sort_by in ["created", "created_at"]:
                base_query += f" ORDER BY b.created_at {order_direction}"
            elif sort_by in ["updated", "updated_at"]:
                base_query += f" ORDER BY b.updated_at {order_direction}"
            elif sort_by == "status":
                status_case = """
                    CASE b.status
                        WHEN 'TODO' THEN 0
                        WHEN 'IN_PROGRESS' THEN 1
                        WHEN 'DONE' THEN 2
                        WHEN 'CANCELED' THEN 3
                        WHEN 'EXTERNAL' THEN 4
                    END"""
                priority_case = """
                    CASE b.priority
                        WHEN 'High' THEN 0
                        WHEN 'Medium' THEN 1
                        WHEN 'Low' THEN 2
                    END"""
                base_query += f"""
                ORDER BY
                    {status_case} {order_direction},
                    {priority_case} {order_direction},
                    b.created_at {reverse_direction}
                """
            else:
                base_query += f" ORDER BY b.created_at {order_direction}"

            # クエリ実行
            rows = fetch_all(conn, base_query, tuple(params))
            items = rows_to_dicts(rows)

            # 総数取得（フィルタなし）
            if all_projects:
                total_row = fetch_all(
                    conn,
                    "SELECT COUNT(*) as count FROM backlog_items",
                    ()
                )
            else:
                total_row = fetch_all(
                    conn,
                    "SELECT COUNT(*) as count FROM backlog_items WHERE project_id = ?",
                    (project_name,)
                )
            total_count = total_row[0]["count"] if total_row else 0

            return ListBacklogResult(
                success=True,
                items=items,
                total_count=total_count,
                filtered_count=len(items),
                message=f"{len(items)}件のBACKLOGを取得しました",
                applied_filters=applied_filters
            )

    except ValidationError as e:
        return ListBacklogResult(
            success=False,
            error=f"入力検証エラー: {e}",
            applied_filters=applied_filters
        )
    except DatabaseError as e:
        return ListBacklogResult(
            success=False,
            error=f"データベースエラー: {e}",
            applied_filters=applied_filters
        )
    except Exception as e:
        return ListBacklogResult(
            success=False,
            error=f"予期しないエラー: {e}",
            applied_filters=applied_filters
        )


def format_table(items: List[Dict[str, Any]], verbose: bool = False, sort_by: str = "priority") -> str:
    """
    BACKLOG一覧をテーブル形式でフォーマット

    sort_order表示時は数値優先度（#1, #2...）を表示し、グループ化する
    その他の表示時は従来フォーマットを維持

    Args:
        items: BACKLOG項目のリスト
        verbose: 詳細表示フラグ
        sort_by: ソート基準（sort_order時に特別表示）

    Returns:
        str: フォーマットされた文字列
    """
    if not items:
        return "BACKLOGがありません"

    lines = []

    # sort_order表示モード: 数値優先度とグルーピング表示
    if sort_by == "sort_order":
        # sort_orderでグループ化
        grouped = {}
        for item in items:
            so = item.get("sort_order", 999)
            if so not in grouped:
                grouped[so] = []
            grouped[so].append(item)

        # グループごとに表示
        for sort_order in sorted(grouped.keys()):
            group_items = grouped[sort_order]

            # グループヘッダ（未設定の999は特別表示）
            if sort_order == 999:
                lines.append(f"\n[優先度未設定] ({len(group_items)}件)")
            else:
                lines.append(f"\n[#{sort_order}] ({len(group_items)}件)")
            lines.append("-" * 80)

            # グループ内のアイテムを表示
            if verbose:
                header = f"  {'ID':<12} {'Status':<12} {'Priority':<8} {'Title':<30} {'ORDER':<12}"
                lines.append(header)

                for item in group_items:
                    line = (
                        f"  {item['id']:<12} "
                        f"{item['status']:<12} "
                        f"{item['priority']:<8} "
                        f"{item['title'][:28]:<30} "
                        f"{item.get('related_order_id') or '-':<12}"
                    )
                    lines.append(line)
            else:
                for item in group_items:
                    line = (
                        f"  {item['id']:<12} "
                        f"{item['status']:<12} "
                        f"{item['priority']:<8} "
                        f"{item['title'][:38]}"
                    )
                    lines.append(line)

        return "\n".join(lines)

    # 通常表示モード（既存フォーマット維持）
    if verbose:
        # 詳細表示
        header = f"{'ID':<12} {'Status':<12} {'Priority':<8} {'Title':<30} {'Related ORDER':<12}"
        lines.append(header)
        lines.append("-" * len(header))

        for item in items:
            line = (
                f"{item['id']:<12} "
                f"{item['status']:<12} "
                f"{item['priority']:<8} "
                f"{item['title'][:28]:<30} "
                f"{item.get('related_order_id') or '-':<12}"
            )
            lines.append(line)
    else:
        # 簡易表示
        header = f"{'ID':<12} {'Status':<12} {'Priority':<8} {'Title':<40}"
        lines.append(header)
        lines.append("-" * len(header))

        for item in items:
            line = (
                f"{item['id']:<12} "
                f"{item['status']:<12} "
                f"{item['priority']:<8} "
                f"{item['title'][:38]:<40}"
            )
            lines.append(line)

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
        description="BACKLOG一覧を取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 全件表示
  python list.py AI_PM_PJ

  # ステータスでフィルタ（単一）
  python list.py AI_PM_PJ --status TODO

  # ステータスでフィルタ（複数）
  python list.py AI_PM_PJ --status TODO IN_PROGRESS

  # 優先度でフィルタ（複数）
  python list.py AI_PM_PJ --priority High Medium

  # 複数条件でフィルタ
  python list.py AI_PM_PJ --status TODO IN_PROGRESS --priority High

  # 優先度順でソート（昇順）
  python list.py AI_PM_PJ --sort priority --order asc

  # 全プロジェクト横断で取得
  python list.py --all --status TODO --priority High

  # JSON形式で出力
  python list.py AI_PM_PJ --json

ソート順:
  priority:   優先度順（High → Medium → Low）
  sort_order: 数値優先度順（1 → 2 → ... → 999）
  created_at: 作成日順
  updated_at: 更新日順
  status:     ステータス順（TODO → IN_PROGRESS → DONE → ...）

ソート方向:
  asc:  昇順
  desc: 降順（デフォルト）
"""
    )

    parser.add_argument(
        "project_name",
        nargs="?",
        default=None,
        help="プロジェクト名 (例: AI_PM_PJ)。--all使用時は省略可"
    )
    parser.add_argument(
        "--category", "-c",
        nargs="+",
        help="カテゴリでフィルタ（複数指定可）"
    )
    parser.add_argument(
        "--status", "-s",
        nargs="+",
        choices=VALID_STATUSES["backlog"],
        help="ステータスでフィルタ（複数指定可）"
    )
    parser.add_argument(
        "--priority", "-p",
        nargs="+",
        choices=VALID_PRIORITIES,
        help="優先度でフィルタ（複数指定可）"
    )
    parser.add_argument(
        "--project",
        help="プロジェクトでフィルタ（--all使用時のみ有効）"
    )
    parser.add_argument(
        "--sort",
        choices=["priority", "created", "created_at", "updated", "updated_at", "status", "sort_order"],
        default="priority",
        help="ソート順（デフォルト: priority）"
    )
    parser.add_argument(
        "--order",
        choices=["asc", "desc"],
        default="desc",
        help="ソート方向（デフォルト: desc）"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="all_projects",
        help="全プロジェクト横断で取得"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="詳細情報を表示"
    )

    args = parser.parse_args()

    # プロジェクト名チェック
    if not args.all_projects and not args.project_name:
        parser.error("プロジェクト名を指定してください（または --all を使用）")

    # デフォルトフィルタの設定（--status未指定時はTODO+IN_PROGRESSのみ表示）
    if args.status is None:
        args.status = ['TODO', 'IN_PROGRESS']

    result = list_backlogs(
        project_name=args.project_name,
        category_filter=args.category,
        status_filter=args.status,
        priority_filter=args.priority,
        project_filter=args.project,
        sort_by=args.sort,
        sort_order=args.order,
        all_projects=args.all_projects,
    )

    if args.json:
        output = {
            "success": result.success,
            "items": result.items,
            "total_count": result.total_count,
            "filtered_count": result.filtered_count,
            "message": result.message,
            "error": result.error,
            "applied_filters": result.applied_filters,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    else:
        if result.success:
            # フィルタ情報を表示
            filters_applied = []
            if result.applied_filters:
                if result.applied_filters.get("status"):
                    filters_applied.append(f"status={result.applied_filters['status']}")
                if result.applied_filters.get("priority"):
                    filters_applied.append(f"priority={result.applied_filters['priority']}")
                if result.applied_filters.get("category"):
                    filters_applied.append(f"category={result.applied_filters['category']}")

            filter_str = f" [フィルタ: {', '.join(filters_applied)}]" if filters_applied else ""
            sort_str = f" (sort: {result.applied_filters.get('sort_by', 'priority')} {result.applied_filters.get('sort_order', 'desc')})"

            print(f"BACKLOG一覧 ({result.filtered_count}/{result.total_count}件){filter_str}{sort_str}")
            print()
            print(format_table(result.items, verbose=args.verbose, sort_by=args.sort))

            # 統計サマリ
            if result.items:
                status_counts = {}
                priority_counts = {}
                for item in result.items:
                    s = item["status"]
                    p = item["priority"]
                    status_counts[s] = status_counts.get(s, 0) + 1
                    priority_counts[p] = priority_counts.get(p, 0) + 1

                print()
                print("ステータス別:")
                for s in ["TODO", "IN_PROGRESS", "DONE", "CANCELED", "EXTERNAL"]:
                    if s in status_counts:
                        print(f"  {s}: {status_counts[s]}件")

                print()
                print("優先度別:")
                for p in ["High", "Medium", "Low"]:
                    if p in priority_counts:
                        print(f"  {p}: {priority_counts[p]}件")
        else:
            print(f"[ERROR] {result.error}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
