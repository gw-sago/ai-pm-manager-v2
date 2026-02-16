"""
AI PM Framework - Worker実行ステップ取得

execute_task.pyの各ステップ（get_task_info/assign_worker/file_lock/execute/create_report）を
実行中タスクから取得するAPIを提供。

ステップ情報はtasksテーブルのstatusおよびworker_metadataカラム、
または最新のchange_historyレコードから推定する。
"""

import json
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

# 内部モジュール
try:
    from utils.db import get_connection, fetch_one, fetch_all, row_to_dict, rows_to_dicts
except ImportError:
    import sys
    _current_dir = Path(__file__).resolve().parent
    _package_root = _current_dir.parent
    if str(_package_root) not in sys.path:
        sys.path.insert(0, str(_package_root))
    from utils.db import get_connection, fetch_one, fetch_all, row_to_dict, rows_to_dicts


# Worker実行ステップの定義（execute_task.pyと同期すること）
EXECUTION_STEPS = [
    "get_task_info",      # タスク情報取得
    "assign_worker",      # Worker割当
    "file_lock",          # ファイルロック取得
    "execute_task",       # AI実行
    "create_report",      # REPORT作成
    "add_review_queue",   # レビューキュー追加
    "update_status_done", # ステータス更新（DONE）
    "auto_review",        # 自動レビュー
]

# ステップ表示名マッピング
STEP_DISPLAY_NAMES = {
    "get_task_info": "タスク情報取得",
    "assign_worker": "Worker割当",
    "file_lock": "ファイルロック",
    "execute_task": "AI実行",
    "create_report": "レポート作成",
    "add_review_queue": "レビュー待ち",
    "update_status_done": "完了処理",
    "auto_review": "自動レビュー",
}


def get_task_execution_step(
    project_id: str,
    task_id: str,
    *,
    verbose: bool = False
) -> Dict[str, Any]:
    """
    タスクの現在の実行ステップを取得

    Args:
        project_id: プロジェクトID
        task_id: タスクID
        verbose: 詳細情報を含めるか

    Returns:
        Dict containing:
            - current_step: 現在のステップ名（EXECUTION_STEPSのいずれか）
            - current_step_display: ステップの表示名
            - step_index: ステップのインデックス（0-based）
            - total_steps: 総ステップ数
            - progress_percent: 進捗率（0-100）
            - status: タスクステータス
            - assignee: 担当Worker
            - started_at: 実行開始日時
            - last_updated: 最終更新日時
            - completed_steps: 完了したステップのリスト（verboseの場合）
            - error: エラー情報（あれば）

    Example:
        >>> step_info = get_task_execution_step("ai_pm_manager", "TASK_1034")
        >>> print(step_info["current_step"])  # "execute_task"
        >>> print(step_info["progress_percent"])  # 37.5
    """
    conn = get_connection()
    try:
        # タスク情報を取得
        task = fetch_one(
            conn,
            """
            SELECT id, status, assignee, updated_at, created_at, metadata
            FROM tasks
            WHERE id = ? AND project_id = ?
            """,
            (task_id, project_id)
        )

        if not task:
            return {
                "error": f"タスクが見つかりません: {task_id}",
                "current_step": None,
                "step_index": -1,
            }

        task_data = row_to_dict(task)
        status = task_data["status"]

        # ステータスがIN_PROGRESSでない場合は、実行中でない
        if status != "IN_PROGRESS":
            return {
                "current_step": None,
                "current_step_display": "実行中でない",
                "step_index": -1,
                "total_steps": len(EXECUTION_STEPS),
                "progress_percent": 0 if status in ("QUEUED", "BLOCKED") else 100,
                "status": status,
                "assignee": task_data.get("assignee"),
                "started_at": None,
                "last_updated": task_data["updated_at"],
            }

        # IN_PROGRESSタスクの場合、change_historyから最新のステップを推定
        change_history = fetch_all(
            conn,
            """
            SELECT action, details, timestamp
            FROM change_history
            WHERE task_id = ? AND project_id = ?
            ORDER BY timestamp DESC
            LIMIT 20
            """,
            (task_id, project_id)
        )

        current_step = _infer_current_step(change_history, task_data)
        step_index = EXECUTION_STEPS.index(current_step) if current_step in EXECUTION_STEPS else 0
        progress_percent = int((step_index + 1) / len(EXECUTION_STEPS) * 100)

        # 実行開始日時を取得（IN_PROGRESSになったタイミング）
        started_at_row = fetch_one(
            conn,
            """
            SELECT timestamp
            FROM change_history
            WHERE task_id = ? AND project_id = ?
              AND action = 'status_change'
              AND details LIKE '%IN_PROGRESS%'
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (task_id, project_id)
        )
        started_at = started_at_row["timestamp"] if started_at_row else task_data["updated_at"]

        result = {
            "current_step": current_step,
            "current_step_display": STEP_DISPLAY_NAMES.get(current_step, current_step),
            "step_index": step_index,
            "total_steps": len(EXECUTION_STEPS),
            "progress_percent": progress_percent,
            "status": status,
            "assignee": task_data.get("assignee"),
            "started_at": started_at,
            "last_updated": task_data["updated_at"],
        }

        # 詳細情報を含める
        if verbose:
            completed_steps = []
            for i in range(step_index):
                completed_steps.append({
                    "step": EXECUTION_STEPS[i],
                    "display": STEP_DISPLAY_NAMES.get(EXECUTION_STEPS[i], EXECUTION_STEPS[i]),
                })
            result["completed_steps"] = completed_steps

        return result

    finally:
        conn.close()


def _infer_current_step(
    change_history: List[sqlite3.Row],
    task_data: Dict[str, Any]
) -> str:
    """
    change_historyとタスクデータから現在のステップを推定

    Args:
        change_history: change_historyレコードのリスト（新しい順）
        task_data: タスクデータ

    Returns:
        推定された現在のステップ名
    """
    if not change_history:
        # 履歴がない場合は最初のステップ
        return "get_task_info"

    # 最新の履歴から推定
    history_dicts = rows_to_dicts(change_history)

    # パターン1: status_changeでIN_PROGRESSになった直後
    for record in history_dicts:
        action = record.get("action", "")
        details = record.get("details", "")

        # DONE遷移があればレビュー待ちステップ
        if action == "status_change" and "DONE" in details:
            return "add_review_queue"

        # Worker割当があればfile_lockステップ
        if action == "assignee_change" or "assignee" in details.lower():
            return "file_lock"

    # パターン2: file_locksテーブルを確認（ロック取得済み＝execute中）
    # これは別途DBクエリが必要なので、ここでは簡易推定
    # metadataにfile_lock情報があるかチェック
    metadata_str = task_data.get("metadata")
    if metadata_str:
        try:
            metadata = json.loads(metadata_str)
            if metadata.get("file_locked"):
                return "execute_task"
        except (json.JSONDecodeError, TypeError):
            pass

    # パターン3: レビューキューに追加されているかチェック（これも別途クエリが必要）
    # ここでは簡易推定として、DONE直前ならcreate_reportステップと推定
    for record in history_dicts:
        if "report" in record.get("details", "").lower():
            return "create_report"

    # デフォルト: IN_PROGRESSになった直後はassign_workerステップ
    return "assign_worker"


def get_multiple_tasks_execution_steps(
    project_id: str,
    task_ids: Optional[List[str]] = None,
    *,
    order_id: Optional[str] = None,
    status_filter: Optional[List[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    複数タスクの実行ステップを一括取得

    Args:
        project_id: プロジェクトID
        task_ids: タスクIDのリスト（Noneの場合は全IN_PROGRESSタスク）
        order_id: ORDER IDでフィルタ（オプション）
        status_filter: ステータスでフィルタ（オプション、デフォルト: ["IN_PROGRESS"]）

    Returns:
        Dict[task_id, step_info]: タスクIDをキーとしたステップ情報の辞書
    """
    conn = get_connection()
    try:
        # クエリ条件を構築
        where_parts = ["project_id = ?"]
        params = [project_id]

        if task_ids:
            placeholders = ",".join(["?"] * len(task_ids))
            where_parts.append(f"id IN ({placeholders})")
            params.extend(task_ids)
        elif status_filter:
            placeholders = ",".join(["?"] * len(status_filter))
            where_parts.append(f"status IN ({placeholders})")
            params.extend(status_filter)
        else:
            # デフォルト: IN_PROGRESSのみ
            where_parts.append("status = ?")
            params.append("IN_PROGRESS")

        if order_id:
            where_parts.append("order_id = ?")
            params.append(order_id)

        where_clause = " AND ".join(where_parts)

        # タスクを取得
        tasks = fetch_all(
            conn,
            f"""
            SELECT id, status, assignee, updated_at, created_at, metadata
            FROM tasks
            WHERE {where_clause}
            ORDER BY updated_at DESC
            """,
            tuple(params)
        )

        result = {}
        for task in tasks:
            task_data = row_to_dict(task)
            task_id = task_data["id"]

            # 各タスクのステップ情報を取得
            step_info = get_task_execution_step(project_id, task_id, verbose=False)
            result[task_id] = step_info

        return result

    finally:
        conn.close()


def format_execution_step_display(step_info: Dict[str, Any]) -> str:
    """
    ステップ情報を表示用にフォーマット

    Args:
        step_info: get_task_execution_step()の戻り値

    Returns:
        フォーマット済み文字列

    Example:
        >>> info = get_task_execution_step("ai_pm_manager", "TASK_1034")
        >>> print(format_execution_step_display(info))
        [3/8] AI実行中 (37%)
    """
    if step_info.get("error"):
        return f"エラー: {step_info['error']}"

    if step_info["current_step"] is None:
        return f"[{step_info['status']}] 実行中でない"

    step_index = step_info["step_index"]
    total_steps = step_info["total_steps"]
    current_display = step_info["current_step_display"]
    progress = step_info["progress_percent"]

    return f"[{step_index + 1}/{total_steps}] {current_display} ({progress}%)"


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python get_execution_steps.py PROJECT_ID TASK_ID")
        print("Example: python get_execution_steps.py ai_pm_manager TASK_1034")
        sys.exit(1)

    project_id = sys.argv[1]
    task_id = sys.argv[2]

    step_info = get_task_execution_step(project_id, task_id, verbose=True)

    print(json.dumps(step_info, ensure_ascii=False, indent=2, default=str))
