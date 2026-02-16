#!/usr/bin/env python3
"""
AI PM Framework - クラッシュ検知・DB修復スクリプト

Workerプロセス異常終了時にDB状態（タスクステータス・ファイルロック）を修復する。

Usage:
    python backend/worker/recover_crashed.py PROJECT_NAME TASK_ID [options]

Options:
    --reason TEXT    クラッシュ理由の説明文
    --json          JSON形式で出力

Example:
    python backend/worker/recover_crashed.py ai_pm_manager TASK_998
    python backend/worker/recover_crashed.py ai_pm_manager TASK_998 --reason "プロセスがタイムアウト"
    python backend/worker/recover_crashed.py ai_pm_manager TASK_998 --json

処理内容:
1. タスクのステータスがIN_PROGRESSであることを確認
2. ステータスをIN_PROGRESS → QUEUEDに戻す
3. 該当タスクのfile_lockレコードを削除
4. change_historyに修復履歴を記録
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

# 内部モジュールインポート
try:
    from utils.db import (
        get_connection, transaction, execute_query, fetch_one,
        row_to_dict, DatabaseError
    )
except ImportError as e:
    print(f"エラー: 内部モジュールのインポートに失敗: {e}", file=sys.stderr)
    sys.exit(1)


def recover_crashed_task(
    project_id: str,
    task_id: str,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """
    クラッシュしたタスクのDB状態を修復する。

    IN_PROGRESSのタスクをQUEUEDに戻し、file_lockを解放し、change_historyに記録する。

    Args:
        project_id: プロジェクトID
        task_id: タスクID
        reason: クラッシュ理由の説明文（Noneの場合はデフォルトメッセージ）

    Returns:
        修復結果の辞書
            - success: True/False
            - task_id: タスクID
            - previous_status: 修復前のステータス
            - new_status: 修復後のステータス (QUEUED)
            - locks_released: 解放したロック数
            - error: エラーメッセージ（失敗時）
    """
    # TASK_XXX 形式に正規化
    if not task_id.startswith("TASK_"):
        task_id = f"TASK_{task_id}"

    # デフォルトの理由
    if reason is None:
        reason = "Workerプロセス異常終了による自動修復"

    try:
        with transaction() as conn:
            # 1. タスクの存在確認とステータス取得
            task_row = fetch_one(
                conn,
                "SELECT id, status, project_id, assignee FROM tasks WHERE id = ? AND project_id = ?",
                (task_id, project_id)
            )

            if task_row is None:
                return {
                    "success": False,
                    "task_id": task_id,
                    "error": f"タスクが見つかりません: {task_id} (project: {project_id})"
                }

            # row_to_dictを使用（BUG_003: sqlite3.Row.get()は使わない）
            task_dict = row_to_dict(task_row)
            current_status = task_dict["status"]

            # 2. IN_PROGRESS以外の場合はスキップ
            if current_status != "IN_PROGRESS":
                return {
                    "success": False,
                    "task_id": task_id,
                    "error": f"タスクのステータスがIN_PROGRESSではありません（現在: {current_status}）。修復対象外です。"
                }

            # 3. ステータスをIN_PROGRESS → QUEUEDに戻す
            now_iso = datetime.now().isoformat()
            execute_query(
                conn,
                "UPDATE tasks SET status = 'QUEUED', updated_at = ? WHERE id = ? AND project_id = ?",
                (now_iso, task_id, project_id)
            )

            # 4. file_lockレコードを削除
            #    削除前にカウントを取得
            lock_count_row = fetch_one(
                conn,
                "SELECT COUNT(*) as count FROM file_locks WHERE project_id = ? AND task_id = ?",
                (project_id, task_id)
            )
            locks_released = lock_count_row["count"] if lock_count_row else 0

            if locks_released > 0:
                execute_query(
                    conn,
                    "DELETE FROM file_locks WHERE project_id = ? AND task_id = ?",
                    (project_id, task_id)
                )

            # 5. change_historyに記録
            execute_query(
                conn,
                """
                INSERT INTO change_history (
                    entity_type, entity_id, project_id, field_name,
                    old_value, new_value, changed_by, change_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "task",
                    task_id,
                    project_id,
                    "status",
                    "IN_PROGRESS",
                    "QUEUED",
                    "System(crash_recovery)",
                    reason,
                )
            )

            # トランザクション正常終了 → 自動コミット

        return {
            "success": True,
            "task_id": task_id,
            "previous_status": "IN_PROGRESS",
            "new_status": "QUEUED",
            "locks_released": locks_released,
        }

    except DatabaseError as e:
        return {
            "success": False,
            "task_id": task_id,
            "error": f"データベースエラー: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "task_id": task_id,
            "error": f"予期しないエラー: {e}",
        }


def main():
    """CLIエントリーポイント"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
        setup_utf8_output()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(
        description="クラッシュしたWorkerタスクのDB状態を修復",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("task_id", help="タスクID（例: 998 または TASK_998）")
    parser.add_argument("--reason", help="クラッシュ理由の説明文")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    result = recover_crashed_task(
        project_id=args.project_id,
        task_id=args.task_id,
        reason=args.reason,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["success"]:
            print(f"[OK] タスク修復完了: {result['task_id']}")
            print(f"  ステータス: {result['previous_status']} -> {result['new_status']}")
            print(f"  解放ロック数: {result['locks_released']}")
        else:
            print(f"[NG] タスク修復失敗: {result['task_id']}", file=sys.stderr)
            print(f"  エラー: {result['error']}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
