#!/usr/bin/env python3
"""
AI PM Framework - 統合ステータススクリプト

1回のPython起動・1回のDB接続で、プロジェクト・ORDER・タスクの全情報を一括取得する。
/aipmコマンドに最適化した軽量データ取得を行い、Python起動コストを削減する。

Usage:
    python backend/status/aipm_status.py                      # アクティブプロジェクトのステータス
    python backend/status/aipm_status.py PROJECT_NAME          # 指定プロジェクトのステータス
    python backend/status/aipm_status.py --all                 # 全プロジェクトのステータス
    python backend/status/aipm_status.py PROJECT_NAME --json   # JSON出力
    python backend/status/aipm_status.py --all --json          # 全プロジェクトJSON出力

Options:
    project_name    プロジェクトID（省略時はアクティブプロジェクト全体）
    --all           非アクティブプロジェクトも含めて表示
    --json          JSON形式で出力
    --perf          パフォーマンス測定を表示

設計思想:
    従来の/aipmコマンドは python backend/project/list.py, order/list.py, task/list.py を
    それぞれ個別に起動していた。Pythonプロセスの起動コスト（0.3-0.5秒）が3回発生するため、
    合計で1-2秒のオーバーヘッドがあった。
    本スクリプトはDB接続1回で全データを取得し、1回のPython起動で完結する。
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def _check_column_exists(conn, table_name: str, column_name: str) -> bool:
    """テーブルに指定カラムが存在するか確認"""
    try:
        result = fetch_all(conn, f"PRAGMA table_info({table_name})")
        column_names = [row["name"] for row in result]
        return column_name in column_names
    except Exception:
        return False


def _build_placeholders(ids: List[str]) -> str:
    """プレースホルダ文字列を生成: ('?', '?', ...) の形式"""
    return "(" + ", ".join("?" for _ in ids) + ")"


def get_unified_status(
    conn,
    *,
    project_id: Optional[str] = None,
    include_all: bool = False,
) -> Dict[str, Any]:
    """
    DB接続1回で全ステータスデータを一括取得するコア関数

    3つのモードに対応:
    - 単一プロジェクトモード: project_id指定時。そのプロジェクトのORDER・タスクを返す
    - アクティブプロジェクトモード: project_id=None, include_all=False。
      IN_PROGRESS/アクティブなプロジェクトを自動検出する
    - 全プロジェクトモード: include_all=True。非アクティブ含め全件返す

    TASK_337最適化:
    - N+1クエリ問題を解消: ORDER統計・タスク統計を GROUP BY project_id でバッチ取得
    - アクティブORDER一覧を全プロジェクト分一括取得
    - タスク一覧を全アクティブORDER分一括取得
    - DRAFT ORDER一覧を IN句で一括取得
    - クエリ数: 従来 O(P*O) → 最適化後 O(1) （P=プロジェクト数, O=ORDER数）

    Args:
        conn: sqlite3.Connection（既に接続済みのDB接続）
        project_id: 指定プロジェクトID（Noneの場合は全プロジェクト）
        include_all: 非アクティブプロジェクトも含めるか

    Returns:
        Dict: 統合ステータスデータ
            - projects: プロジェクト一覧（ORDER・タスク統計付き）
            - draft_orders: DRAFTステータスのORDER一覧
            - backlog_summary: バックログ概要
            - metadata: メタ情報（取得日時、データソース、クエリ数等）
    """
    query_count = 0
    has_is_active = _check_column_exists(conn, "projects", "is_active")
    has_dev_workspace = _check_column_exists(conn, "projects", "dev_workspace_path")
    query_count += 2  # PRAGMA table_info x2

    # ============================================================
    # 1. プロジェクト一覧取得
    # ============================================================
    dev_ws_col = ", p.dev_workspace_path" if has_dev_workspace else ""
    is_active_col = ", p.is_active" if has_is_active else ""

    projects_query = f"""
    SELECT
        p.id,
        p.name,
        p.path,
        p.status,
        p.current_order_id,
        p.created_at,
        p.updated_at
        {is_active_col}
        {dev_ws_col}
    FROM projects p
    WHERE 1=1
    """
    params: List[Any] = []

    if project_id:
        # 単一プロジェクトモード: 指定IDのみ
        projects_query += " AND p.id = ?"
        params.append(project_id)
    elif has_is_active and not include_all:
        # アクティブプロジェクトモード: is_active=1のみ
        projects_query += " AND p.is_active = 1"
    # else: 全プロジェクトモード: フィルタなし

    projects_query += """
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

    project_rows = fetch_all(conn, projects_query, tuple(params) if params else None)
    projects = rows_to_dicts(project_rows)
    query_count += 1

    # is_activeカラムがない場合のデフォルト値
    if not has_is_active:
        for p in projects:
            p["is_active"] = True

    # プロジェクトが0件なら以降のクエリは全てスキップ
    if not projects:
        from datetime import datetime
        return {
            "projects": [],
            "draft_orders": [],
            "backlog_summary": {},
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "data_source": "sqlite",
                "mode": "single_project" if project_id else ("all" if include_all else "active_only"),
                "query_count": query_count,
            },
        }

    # ============================================================
    # 2. ORDER・タスク統計をバッチ取得（N+1解消）
    # ============================================================
    project_ids = [p["id"] for p in projects]
    placeholders = _build_placeholders(project_ids)

    # --- ORDER統計: 1クエリで全プロジェクト分取得 ---
    order_stats_rows = fetch_all(
        conn,
        f"""
        SELECT
            project_id,
            COUNT(*) as total_orders,
            SUM(CASE WHEN status IN ('PLANNING', 'IN_PROGRESS', 'REVIEW') THEN 1 ELSE 0 END) as active_orders,
            SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed_orders,
            SUM(CASE WHEN status = 'DRAFT' THEN 1 ELSE 0 END) as draft_orders
        FROM orders
        WHERE project_id IN {placeholders}
        GROUP BY project_id
        """,
        tuple(project_ids)
    )
    query_count += 1
    order_stats_map: Dict[str, Dict[str, int]] = {}
    for row in order_stats_rows:
        order_stats_map[row["project_id"]] = {
            "total_orders": row["total_orders"] or 0,
            "active_orders": row["active_orders"] or 0,
            "completed_orders": row["completed_orders"] or 0,
            "draft_orders": row["draft_orders"] or 0,
        }

    # --- タスク統計: 1クエリで全プロジェクト分取得 ---
    task_stats_rows = fetch_all(
        conn,
        f"""
        SELECT
            project_id,
            COUNT(*) as total_tasks,
            SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed_tasks,
            SUM(CASE WHEN status = 'IN_PROGRESS' THEN 1 ELSE 0 END) as in_progress_tasks,
            SUM(CASE WHEN status = 'BLOCKED' THEN 1 ELSE 0 END) as blocked_tasks,
            SUM(CASE WHEN status = 'REWORK' THEN 1 ELSE 0 END) as rework_tasks,
            SUM(CASE WHEN status = 'QUEUED' THEN 1 ELSE 0 END) as queued_tasks,
            SUM(CASE WHEN status = 'DONE' THEN 1 ELSE 0 END) as done_tasks
        FROM tasks
        WHERE project_id IN {placeholders}
        GROUP BY project_id
        """,
        tuple(project_ids)
    )
    query_count += 1
    task_stats_map: Dict[str, Dict[str, int]] = {}
    for row in task_stats_rows:
        task_stats_map[row["project_id"]] = {
            "total_tasks": row["total_tasks"] or 0,
            "completed_tasks": row["completed_tasks"] or 0,
            "in_progress_tasks": row["in_progress_tasks"] or 0,
            "blocked_tasks": row["blocked_tasks"] or 0,
            "rework_tasks": row["rework_tasks"] or 0,
            "queued_tasks": row["queued_tasks"] or 0,
            "done_tasks": row["done_tasks"] or 0,
        }

    # プロジェクトに統計を紐付け
    for project in projects:
        pid = project["id"]
        os = order_stats_map.get(pid, {})
        project["order_count"] = os.get("total_orders", 0)
        project["active_order_count"] = os.get("active_orders", 0)
        project["completed_order_count"] = os.get("completed_orders", 0)
        project["draft_order_count"] = os.get("draft_orders", 0)

        ts = task_stats_map.get(pid, {})
        total_tasks = ts.get("total_tasks", 0)
        completed_tasks = ts.get("completed_tasks", 0)
        project["task_count"] = total_tasks
        project["completed_task_count"] = completed_tasks
        project["in_progress_task_count"] = ts.get("in_progress_tasks", 0)
        project["blocked_task_count"] = ts.get("blocked_tasks", 0)
        project["rework_task_count"] = ts.get("rework_tasks", 0)
        project["queued_task_count"] = ts.get("queued_tasks", 0)
        project["done_task_count"] = ts.get("done_tasks", 0)
        project["task_progress_percent"] = (
            round((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
        )

    # ============================================================
    # 3. アクティブORDER一覧をバッチ取得（N+1解消）
    # ============================================================
    active_orders_rows = fetch_all(
        conn,
        f"""
        SELECT
            o.project_id,
            o.id,
            o.title,
            o.priority,
            o.status,
            o.sort_order,
            o.started_at,
            o.created_at,
            o.updated_at,
            COUNT(t.id) as task_count,
            SUM(CASE WHEN t.status = 'COMPLETED' THEN 1 ELSE 0 END) as completed_task_count,
            SUM(CASE WHEN t.status = 'IN_PROGRESS' THEN 1 ELSE 0 END) as in_progress_task_count,
            SUM(CASE WHEN t.status = 'DONE' THEN 1 ELSE 0 END) as done_task_count
        FROM orders o
        LEFT JOIN tasks t ON t.order_id = o.id AND t.project_id = o.project_id
        WHERE o.project_id IN {placeholders}
          AND o.status IN ('PLANNING', 'IN_PROGRESS', 'REVIEW')
        GROUP BY o.project_id, o.id
        ORDER BY
            o.project_id,
            CASE o.status
                WHEN 'IN_PROGRESS' THEN 0
                WHEN 'REVIEW' THEN 1
                WHEN 'PLANNING' THEN 2
            END,
            CASE o.priority
                WHEN 'P0' THEN 0
                WHEN 'P1' THEN 1
                WHEN 'P2' THEN 2
            END,
            o.created_at DESC
        """,
        tuple(project_ids)
    )
    query_count += 1
    all_active_orders = rows_to_dicts(active_orders_rows)

    # project_id -> [orders] のマップを構築
    active_orders_by_project: Dict[str, List[Dict[str, Any]]] = {pid: [] for pid in project_ids}
    # アクティブORDERのID一覧を収集（タスク一括取得用）
    active_order_keys: List[tuple] = []  # (project_id, order_id)

    for order in all_active_orders:
        tc = order["task_count"] or 0
        cc = order["completed_task_count"] or 0
        order["progress_percent"] = round((cc / tc) * 100) if tc > 0 else 0
        pid = order["project_id"]
        active_orders_by_project[pid].append(order)
        active_order_keys.append((pid, order["id"]))

    for project in projects:
        project["active_orders"] = active_orders_by_project.get(project["id"], [])

    # ============================================================
    # 4. 各アクティブORDERのタスク一覧をバッチ取得（N+1の中のN+1を解消）
    # ============================================================
    if active_order_keys:
        # (project_id, order_id) ペアのOR条件を構築
        # SQLiteではIN句にタプルを使えないため、OR条件で代替
        where_parts = []
        task_params: List[str] = []
        for pid, oid in active_order_keys:
            where_parts.append("(t.project_id = ? AND t.order_id = ?)")
            task_params.extend([pid, oid])

        where_clause = " OR ".join(where_parts)

        all_tasks_rows = fetch_all(
            conn,
            f"""
            SELECT
                t.project_id,
                t.order_id,
                t.id,
                t.title,
                t.status,
                t.assignee,
                t.priority,
                t.updated_at
            FROM tasks t
            WHERE {where_clause}
            ORDER BY
                t.project_id,
                t.order_id,
                CASE t.status
                    WHEN 'IN_PROGRESS' THEN 0
                    WHEN 'REWORK' THEN 1
                    WHEN 'DONE' THEN 2
                    WHEN 'QUEUED' THEN 3
                    WHEN 'BLOCKED' THEN 4
                    WHEN 'INTERRUPTED' THEN 5
                    WHEN 'COMPLETED' THEN 6
                END,
                CASE t.priority
                    WHEN 'P0' THEN 0
                    WHEN 'P1' THEN 1
                    WHEN 'P2' THEN 2
                END,
                t.created_at
            """,
            tuple(task_params)
        )
        query_count += 1
        all_tasks = rows_to_dicts(all_tasks_rows)

        # (project_id, order_id) -> [tasks] のマップを構築
        tasks_by_order: Dict[str, List[Dict[str, Any]]] = {}
        for task in all_tasks:
            key = f"{task['project_id']}:{task['order_id']}"
            if key not in tasks_by_order:
                tasks_by_order[key] = []
            tasks_by_order[key].append(task)

        # 各アクティブORDERにタスクを紐付け
        for project in projects:
            for order in project["active_orders"]:
                key = f"{project['id']}:{order['id']}"
                order["tasks"] = tasks_by_order.get(key, [])
    else:
        # アクティブORDERがない場合はタスク取得をスキップ
        for project in projects:
            for order in project.get("active_orders", []):
                order["tasks"] = []

    # ============================================================
    # 5. DRAFT ORDER一覧をバッチ取得（N+1解消）
    # ============================================================
    draft_orders_rows = fetch_all(
        conn,
        f"""
        SELECT
            o.id,
            o.project_id,
            o.title,
            o.priority,
            o.status,
            o.sort_order,
            o.description,
            o.created_at,
            o.updated_at
        FROM orders o
        WHERE o.project_id IN {placeholders} AND o.status = 'DRAFT'
        ORDER BY o.project_id, o.sort_order, o.created_at DESC
        """,
        tuple(project_ids)
    )
    query_count += 1
    draft_orders_result = rows_to_dicts(draft_orders_rows)

    # ============================================================
    # 6. バックログ概要
    # ============================================================
    backlog_summary = {}
    try:
        backlog_stats = fetch_one(
            conn,
            """
            SELECT
                COUNT(*) as total_items,
                SUM(CASE WHEN status = 'TODO' THEN 1 ELSE 0 END) as todo_count,
                SUM(CASE WHEN status = 'IN_PROGRESS' THEN 1 ELSE 0 END) as in_progress_count,
                SUM(CASE WHEN priority = 'High' THEN 1 ELSE 0 END) as high_priority_count
            FROM backlog_items
            """
        )
        query_count += 1
        if backlog_stats:
            backlog_summary = {
                "total_items": backlog_stats["total_items"] or 0,
                "todo_count": backlog_stats["todo_count"] or 0,
                "in_progress_count": backlog_stats["in_progress_count"] or 0,
                "high_priority_count": backlog_stats["high_priority_count"] or 0,
            }

            # プロジェクト別バックログ件数
            if project_id:
                proj_backlog = fetch_one(
                    conn,
                    """
                    SELECT COUNT(*) as count
                    FROM backlog_items
                    WHERE project_id = ? AND status IN ('TODO', 'IN_PROGRESS')
                    """,
                    (project_id,)
                )
                query_count += 1
                backlog_summary["project_active_count"] = (
                    proj_backlog["count"] if proj_backlog else 0
                )
            else:
                proj_backlog_rows = fetch_all(
                    conn,
                    """
                    SELECT project_id, COUNT(*) as count
                    FROM backlog_items
                    WHERE status IN ('TODO', 'IN_PROGRESS')
                    GROUP BY project_id
                    """
                )
                query_count += 1
                backlog_summary["by_project"] = {
                    row["project_id"]: row["count"]
                    for row in proj_backlog_rows
                }
    except DatabaseError:
        # backlog_itemsテーブルが存在しない場合はスキップ
        backlog_summary = {"total_items": 0, "note": "backlog_items table not available"}

    # ============================================================
    # 7. メタデータ
    # ============================================================
    from datetime import datetime
    metadata = {
        "timestamp": datetime.now().isoformat(),
        "data_source": "sqlite",
        "mode": "single_project" if project_id else ("all" if include_all else "active_only"),
        "query_count": query_count,
        "project_count": len(projects),
    }

    return {
        "projects": projects,
        "draft_orders": draft_orders_result,
        "backlog_summary": backlog_summary,
        "metadata": metadata,
    }


# ============================================================
# モード別ヘルパー関数
# ============================================================


def get_single_project_status(conn, project_id: str) -> Dict[str, Any]:
    """
    単一プロジェクトモード: 指定プロジェクトのステータスを取得

    Args:
        conn: sqlite3.Connection
        project_id: プロジェクトID

    Returns:
        Dict: 統合ステータスデータ（metadata.mode = "single_project"）
    """
    return get_unified_status(conn, project_id=project_id)


def get_active_projects_status(conn) -> Dict[str, Any]:
    """
    アクティブプロジェクトモード: is_active=1のプロジェクトを自動検出して返す

    Args:
        conn: sqlite3.Connection

    Returns:
        Dict: 統合ステータスデータ（metadata.mode = "active_only"）
    """
    return get_unified_status(conn, include_all=False)


def get_all_projects_status(conn) -> Dict[str, Any]:
    """
    全プロジェクトモード: 非アクティブ含め全プロジェクトのステータスを返す

    Args:
        conn: sqlite3.Connection

    Returns:
        Dict: 統合ステータスデータ（metadata.mode = "all"）
    """
    return get_unified_status(conn, include_all=True)


def format_human_readable(data: Dict[str, Any]) -> str:
    """
    統合ステータスデータを人間が読みやすい形式にフォーマット

    Args:
        data: get_unified_status() の戻り値

    Returns:
        str: フォーマット済みテキスト
    """
    lines: List[str] = []

    projects = data["projects"]
    draft_orders = data["draft_orders"]
    backlog_summary = data["backlog_summary"]
    metadata = data["metadata"]

    mode = metadata.get("mode", "active_only")

    # ヘッダー
    lines.append("=" * 60)
    lines.append("AI PM Framework - Project Status")
    lines.append("=" * 60)

    if not projects:
        lines.append("")
        lines.append("プロジェクトが見つかりません。")
        return "\n".join(lines)

    # --- プロジェクト一覧 ---
    for proj in projects:
        lines.append("")
        active_mark = "" if proj.get("is_active", True) else " (inactive)"
        lines.append(f"### {proj['name']}{active_mark}")
        lines.append(f"  ID: {proj['id']}")
        lines.append(f"  ステータス: {proj['status']}")
        lines.append(
            f"  タスク進捗: {proj['task_progress_percent']}% "
            f"({proj['completed_task_count']}/{proj['task_count']})"
        )
        lines.append(
            f"  ORDER: 合計{proj['order_count']} / "
            f"アクティブ{proj['active_order_count']} / "
            f"DRAFT{proj['draft_order_count']} / "
            f"完了{proj['completed_order_count']}"
        )

        if proj.get("in_progress_task_count", 0) > 0:
            lines.append(f"  実行中タスク: {proj['in_progress_task_count']}件")
        if proj.get("blocked_task_count", 0) > 0:
            lines.append(f"  BLOCKEDタスク: {proj['blocked_task_count']}件")
        if proj.get("rework_task_count", 0) > 0:
            lines.append(f"  REWORKタスク: {proj['rework_task_count']}件")
        if proj.get("done_task_count", 0) > 0:
            lines.append(f"  レビュー待ち(DONE): {proj['done_task_count']}件")

        # --- アクティブORDER ---
        active_orders = proj.get("active_orders", [])
        if active_orders:
            lines.append("")
            lines.append("  [アクティブORDER]")
            for order in active_orders:
                tc = order.get("task_count", 0)
                cc = order.get("completed_task_count", 0)
                pp = order.get("progress_percent", 0)
                lines.append(
                    f"    {order['id']}: {order['title']}"
                )
                lines.append(
                    f"      ステータス: {order['status']} | "
                    f"優先度: {order['priority']} | "
                    f"進捗: {pp}% ({cc}/{tc})"
                )

                # タスク一覧
                tasks = order.get("tasks", [])
                if tasks:
                    for task in tasks:
                        assignee = task.get("assignee") or "-"
                        lines.append(
                            f"      - {task['id']}: {task['title']} "
                            f"[{task['status']}] ({task['priority']}) 担当: {assignee}"
                        )
        else:
            lines.append("")
            lines.append("  [アクティブORDERなし]")

    # --- DRAFT ORDER一覧 ---
    if draft_orders:
        lines.append("")
        lines.append("-" * 60)
        lines.append("### DRAFT ORDER（バックログ）")
        lines.append("")
        for draft in draft_orders:
            lines.append(
                f"  {draft['id']} ({draft['project_id']}): {draft['title']} "
                f"[{draft['priority']}] (作成: {draft['created_at'][:10] if draft.get('created_at') else '-'})"
            )

    # --- バックログ概要 ---
    if backlog_summary and backlog_summary.get("total_items", 0) > 0:
        lines.append("")
        lines.append("-" * 60)
        lines.append("### バックログ概要")
        lines.append(f"  合計: {backlog_summary['total_items']}件")
        lines.append(f"  TODO: {backlog_summary.get('todo_count', 0)}件")
        lines.append(f"  IN_PROGRESS: {backlog_summary.get('in_progress_count', 0)}件")
        lines.append(f"  High優先: {backlog_summary.get('high_priority_count', 0)}件")

    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)


def main():
    """CLIエントリーポイント"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
    except ImportError:
        sys.path.insert(0, str(_package_root))
        from config import setup_utf8_output
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="AI PM Framework 統合ステータス取得（1回のDB接続で全データ取得）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # アクティブプロジェクトのステータス
  python backend/status/aipm_status.py

  # 指定プロジェクトのステータス
  python backend/status/aipm_status.py ai_pm_manager_v2

  # 全プロジェクトのステータス（非アクティブ含む）
  python backend/status/aipm_status.py --all

  # JSON形式で出力
  python backend/status/aipm_status.py ai_pm_manager_v2 --json

  # 全プロジェクトJSON出力
  python backend/status/aipm_status.py --all --json

  # パフォーマンス測定付き
  python backend/status/aipm_status.py --perf
        """
    )

    parser.add_argument(
        "project_name",
        nargs="?",
        default=None,
        help="プロジェクトID（省略時はアクティブプロジェクト全体）",
    )
    parser.add_argument(
        "--all",
        dest="include_all",
        action="store_true",
        help="非アクティブプロジェクトも含めて表示",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力",
    )
    parser.add_argument(
        "--perf",
        action="store_true",
        help="パフォーマンス測定を表示",
    )

    args = parser.parse_args()

    try:
        start_time = time.time()

        # DB接続は1回のみ
        conn = get_connection()
        try:
            data = get_unified_status(
                conn,
                project_id=args.project_name,
                include_all=args.include_all,
            )
        finally:
            conn.close()

        elapsed = time.time() - start_time

        if args.perf:
            qc = data.get("metadata", {}).get("query_count", "?")
            pc = data.get("metadata", {}).get("project_count", "?")
            print(
                f"[PERF] get_unified_status: {elapsed:.3f}s "
                f"(queries={qc}, projects={pc})",
                file=sys.stderr,
            )

        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        else:
            print(format_human_readable(data))

    except DatabaseError as e:
        print(f"DBエラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
