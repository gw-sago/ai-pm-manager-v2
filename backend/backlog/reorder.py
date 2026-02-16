#!/usr/bin/env python3
"""
AI PM Framework - BACKLOG再整理スクリプト

Usage:
    python backend/backlog/reorder.py PROJECT_NAME [options]

Options:
    --dry-run       実際の更新は行わず、プレビューのみ表示
    --json          JSON形式で出力
    --verbose       詳細情報を表示

Example:
    python backend/backlog/reorder.py ai_pm_manager
    python backend/backlog/reorder.py ai_pm_manager --dry-run --verbose
    python backend/backlog/reorder.py ai_pm_manager --json

Reordering Logic:
    1. IN_PROGRESS items → sort_order=0 (最上位固定)
    2. Priority: High → Medium → Low
    3. Within same priority: 依存関係順（前提未達は後ろ）
    4. DONE/CANCELED/EXTERNAL items → 最後（sort_order=9900+）
"""

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Set

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import (
    get_connection,
    transaction,
    execute_query,
    fetch_one,
    fetch_all,
    rows_to_dicts,
    DatabaseError,
)
from utils.validation import (
    validate_project_name,
    project_exists,
    ValidationError,
)


# 優先度の順序
PRIORITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}

# ステータスの重み（アクティブなもの vs 完了したもの）
ACTIVE_STATUSES = {"TODO", "IN_PROGRESS"}
COMPLETED_STATUSES = {"DONE", "CANCELED", "EXTERNAL"}


@dataclass
class ReorderResult:
    """BACKLOG再整理結果"""
    success: bool
    updated_count: int = 0
    total_count: int = 0
    changes: List[Dict[str, Any]] = field(default_factory=list)
    message: str = ""
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


def get_order_status(conn, order_id: str) -> Optional[str]:
    """
    ORDER IDからステータスを取得

    Args:
        conn: データベース接続
        order_id: ORDER ID

    Returns:
        ORDERステータス（存在しない場合はNone）
    """
    if not order_id:
        return None

    row = fetch_one(
        conn,
        "SELECT status FROM orders WHERE id = ?",
        (order_id,)
    )
    return row["status"] if row else None


def build_dependency_graph(items: List[Dict[str, Any]]) -> Dict[str, Set[str]]:
    """
    依存関係グラフを構築

    Args:
        items: BACKLOG項目のリスト

    Returns:
        依存関係マップ（backlog_id → {依存先のrelated_order_ids}）

    Note:
        現在のスキーマではBACKLOG間の明示的な依存関係は存在しないため、
        related_order_idベースで依存を推測する
    """
    # TODO: 将来的にBACKLOG間の依存関係テーブルが追加された場合はそちらを使用
    dependencies: Dict[str, Set[str]] = defaultdict(set)

    # 現状は明示的な依存はないので、空のマップを返す
    return dependencies


def calculate_dependency_depth(
    backlog_id: str,
    dependencies: Dict[str, Set[str]],
    completed_orders: Set[str],
    memo: Optional[Dict[str, int]] = None
) -> int:
    """
    依存関係の深さを計算（トポロジカルソート用）

    Args:
        backlog_id: BACKLOG ID
        dependencies: 依存関係マップ
        completed_orders: 完了済みORDER IDのセット
        memo: メモ化用辞書

    Returns:
        依存の深さ（0=依存なし、1+=依存あり）
    """
    if memo is None:
        memo = {}

    if backlog_id in memo:
        return memo[backlog_id]

    # 依存関係がない、または全ての依存が完了済み
    deps = dependencies.get(backlog_id, set())
    unmet_deps = deps - completed_orders

    if not unmet_deps:
        memo[backlog_id] = 0
        return 0

    # 未完了の依存がある場合、その最大深さ + 1
    max_depth = 0
    for dep_order_id in unmet_deps:
        # 依存先のORDERを持つBACKLOGを探す（簡略化のため、深さ1と仮定）
        max_depth = max(max_depth, 1)

    memo[backlog_id] = max_depth + 1
    return max_depth + 1


def reorder_backlog(
    project_name: str,
    *,
    dry_run: bool = False,
    db_path: Optional[Path] = None,
) -> ReorderResult:
    """
    BACKLOGのsort_orderを再計算

    Args:
        project_name: プロジェクト名
        dry_run: Trueの場合、実際の更新は行わずプレビューのみ
        db_path: データベースパス（テスト用）

    Returns:
        ReorderResult: 再整理結果

    Reordering Logic:
        1. IN_PROGRESS → sort_order=0（最上位固定）
        2. High/Medium/Low優先度順
        3. 同一priority内は依存関係順（前提未達は後ろ）
        4. DONE/CANCELED/EXTERNAL → 最後（9900+）
    """
    try:
        # 入力検証
        validate_project_name(project_name)

        with transaction(db_path=db_path) as conn:
            # プロジェクト存在確認
            if not project_exists(conn, project_name):
                return ReorderResult(
                    success=False,
                    error=f"プロジェクトが見つかりません: {project_name}"
                )

            # 全BACKLOG項目を取得
            rows = fetch_all(
                conn,
                """
                SELECT
                    b.id,
                    b.priority,
                    b.status,
                    b.sort_order as current_sort_order,
                    b.related_order_id,
                    b.title
                FROM backlog_items b
                WHERE b.project_id = ?
                ORDER BY b.id
                """,
                (project_name,)
            )

            items = rows_to_dicts(rows)

            if not items:
                return ReorderResult(
                    success=True,
                    total_count=0,
                    message="対象のBACKLOG項目がありません"
                )

            # 完了済みORDERのセットを作成
            order_rows = fetch_all(
                conn,
                """
                SELECT id, status
                FROM orders
                WHERE project_id = ? AND status = 'COMPLETED'
                """,
                (project_name,)
            )
            completed_orders = {row["id"] for row in rows_to_dicts(order_rows)}

            # 依存関係グラフを構築
            dependencies = build_dependency_graph(items)

            # グループ分け
            in_progress_items = []
            active_items_by_priority = {"High": [], "Medium": [], "Low": []}
            completed_items = []

            for item in items:
                status = item["status"]
                priority = item.get("priority", "Medium")

                if status == "IN_PROGRESS":
                    in_progress_items.append(item)
                elif status in COMPLETED_STATUSES:
                    completed_items.append(item)
                else:  # TODO
                    if priority not in active_items_by_priority:
                        priority = "Medium"  # フォールバック
                    active_items_by_priority[priority].append(item)

            # 各グループ内で依存関係順にソート
            memo: Dict[str, int] = {}

            for priority in ["High", "Medium", "Low"]:
                priority_items = active_items_by_priority[priority]
                priority_items.sort(
                    key=lambda x: (
                        calculate_dependency_depth(
                            x["id"],
                            dependencies,
                            completed_orders,
                            memo
                        ),
                        x["id"]  # 依存深さが同じ場合はID順
                    )
                )

            # sort_orderを割り当て
            changes = []
            sort_order = 0

            # 1. IN_PROGRESS items → sort_order=0
            for item in in_progress_items:
                new_sort_order = 0
                if item["current_sort_order"] != new_sort_order:
                    changes.append({
                        "backlog_id": item["id"],
                        "title": item["title"],
                        "status": item["status"],
                        "priority": item["priority"],
                        "old_sort_order": item["current_sort_order"],
                        "new_sort_order": new_sort_order,
                    })
                    item["new_sort_order"] = new_sort_order

            # 2. High → Medium → Low（依存関係順）
            sort_order = 1
            for priority in ["High", "Medium", "Low"]:
                for item in active_items_by_priority[priority]:
                    new_sort_order = sort_order
                    if item["current_sort_order"] != new_sort_order:
                        changes.append({
                            "backlog_id": item["id"],
                            "title": item["title"],
                            "status": item["status"],
                            "priority": item["priority"],
                            "old_sort_order": item["current_sort_order"],
                            "new_sort_order": new_sort_order,
                        })
                        item["new_sort_order"] = new_sort_order
                    sort_order += 1

            # 3. DONE/CANCELED/EXTERNAL → 最後（9900+）
            sort_order = 9900
            for item in completed_items:
                new_sort_order = sort_order
                if item["current_sort_order"] != new_sort_order:
                    changes.append({
                        "backlog_id": item["id"],
                        "title": item["title"],
                        "status": item["status"],
                        "priority": item["priority"],
                        "old_sort_order": item["current_sort_order"],
                        "new_sort_order": new_sort_order,
                    })
                    item["new_sort_order"] = new_sort_order
                sort_order += 1

            # dry_runでない場合は実際に更新
            if not dry_run and changes:
                now = datetime.now().isoformat()
                for change in changes:
                    execute_query(
                        conn,
                        """
                        UPDATE backlog_items
                        SET sort_order = ?, updated_at = ?
                        WHERE id = ? AND project_id = ?
                        """,
                        (change["new_sort_order"], now, change["backlog_id"], project_name)
                    )

            message = f"BACKLOG再整理が完了しました: {len(changes)}件を更新"
            if dry_run:
                message += " (dry-run mode)"

            return ReorderResult(
                success=True,
                updated_count=len(changes),
                total_count=len(items),
                changes=changes,
                message=message
            )

    except ValidationError as e:
        return ReorderResult(
            success=False,
            error=f"入力検証エラー: {e}"
        )
    except DatabaseError as e:
        return ReorderResult(
            success=False,
            error=f"データベースエラー: {e}"
        )
    except Exception as e:
        return ReorderResult(
            success=False,
            error=f"予期しないエラー: {e}"
        )


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
        description="BACKLOG再整理（sort_order再計算）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 実際に再整理を実行
  python reorder.py ai_pm_manager

  # プレビューのみ（更新なし）
  python reorder.py ai_pm_manager --dry-run --verbose

  # JSON形式で出力
  python reorder.py ai_pm_manager --json

再整理ロジック:
  1. IN_PROGRESS → sort_order=0（最上位固定）
  2. TODO → priority順（High → Medium → Low）
  3. 同一priority内は依存関係順（前提未達は後ろ）
  4. DONE/CANCELED/EXTERNAL → 最後（9900+）
"""
    )

    parser.add_argument(
        "project_name",
        help="プロジェクト名 (例: ai_pm_manager)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実際の更新は行わず、プレビューのみ表示"
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

    result = reorder_backlog(
        project_name=args.project_name,
        dry_run=args.dry_run,
    )

    if args.json:
        output = {
            "success": result.success,
            "updated_count": result.updated_count,
            "total_count": result.total_count,
            "changes": result.changes,
            "message": result.message,
            "error": result.error,
            "warnings": result.warnings,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        if result.success:
            print(f"[OK] {result.message}")
            print(f"  総件数: {result.total_count}")
            print(f"  更新件数: {result.updated_count}")

            if args.verbose and result.changes:
                print()
                print("変更内容:")
                print(f"{'ID':<15} {'Status':<12} {'Priority':<8} {'Old':<5} {'New':<5} {'Title':<40}")
                print("-" * 90)
                for change in result.changes:
                    print(
                        f"{change['backlog_id']:<15} "
                        f"{change['status']:<12} "
                        f"{change['priority']:<8} "
                        f"{change['old_sort_order']:<5} "
                        f"{change['new_sort_order']:<5} "
                        f"{change['title'][:38]:<40}"
                    )
            elif result.updated_count == 0:
                print("  （変更なし - 既に最適な状態です）")
        else:
            print(f"[ERROR] {result.error}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
