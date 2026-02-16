#!/usr/bin/env python3
"""
AI PM Framework - タスクステータスリセットスクリプト

タイムアウトまたは手動停止時にタスクをQUEUED状態に戻す。
ファイルロックも解放する。

Usage:
    python backend/task/reset_status.py PROJECT_ID TASK_ID [options]

Options:
    --reason            リセット理由（デフォルト: "Timeout or manual stop"）
    --json              JSON形式で出力
    --verbose           詳細ログ出力

Example:
    python backend/task/reset_status.py ai_pm_manager TASK_964 --reason "Execution timeout"
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# aipm-db は Python パッケージ名として使えないためモジュール直接参照
try:
    from aipm_db.utils.db import (
        get_connection, transaction, execute_query, fetch_one,
        row_to_dict, DatabaseError
    )
    from aipm_db.utils.validation import (
        validate_project_name, validate_task_id,
        task_exists, ValidationError
    )
    from aipm_db.utils.transition import (
        validate_transition, record_transition, TransitionError
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from utils.db import (
        get_connection, transaction, execute_query, fetch_one,
        row_to_dict, DatabaseError
    )
    from utils.validation import (
        validate_project_name, validate_task_id,
        task_exists, ValidationError
    )
    from utils.transition import (
        validate_transition, record_transition, TransitionError
    )


def reset_task_status(
    project_id: str,
    task_id: str,
    reason: str = "Timeout or manual stop",
    verbose: bool = False
) -> Dict[str, Any]:
    """
    タスクステータスをQUEUEDに戻す（タイムアウト/停止時のリカバリ）

    Args:
        project_id: プロジェクトID
        task_id: タスクID
        reason: リセット理由
        verbose: 詳細ログ出力

    Returns:
        更新されたタスク情報

    Raises:
        ValidationError: 入力検証エラー
        TransitionError: 状態遷移エラー
        DatabaseError: DB操作エラー
    """
    # 入力検証
    validate_project_name(project_id)
    validate_task_id(task_id)

    with transaction() as conn:
        # タスク存在確認
        if not task_exists(conn, task_id, project_id):
            raise ValidationError(
                f"タスクが見つかりません: {task_id} (project: {project_id})",
                "task_id",
                task_id
            )

        # 現在のタスク情報を取得
        current = fetch_one(
            conn,
            "SELECT * FROM tasks WHERE id = ? AND project_id = ?",
            (task_id, project_id)
        )

        if not current:
            raise ValidationError(
                f"タスクが見つかりません: {task_id} (project: {project_id})",
                "task_id",
                task_id
            )

        current_dict = dict(current)
        current_status = current_dict["status"]

        if verbose:
            print(f"[DEBUG] Current status: {current_status}", file=sys.stderr)

        # IN_PROGRESSでない場合はスキップ
        if current_status != "IN_PROGRESS":
            if verbose:
                print(
                    f"[INFO] Task {task_id} is not IN_PROGRESS (current: {current_status}), skipping reset",
                    file=sys.stderr
                )
            return current_dict

        # IN_PROGRESS → QUEUED への遷移を検証
        try:
            validate_transition(conn, "task", current_status, "QUEUED", "System")
        except TransitionError as e:
            # 遷移が許可されていない場合はエラー
            raise TransitionError(
                f"Status transition not allowed: {current_status} -> QUEUED. {str(e)}"
            )

        # ステータスをQUEUEDに更新
        execute_query(
            conn,
            """
            UPDATE tasks
            SET status = 'QUEUED',
                updated_at = ?
            WHERE id = ? AND project_id = ?
            """,
            (datetime.now().isoformat(), task_id, project_id)
        )

        # 状態遷移履歴を記録
        record_transition(
            conn,
            "task",
            task_id,
            current_status,
            "QUEUED",
            "System",
            reason
        )

        # ファイルロック解放（もしあれば）
        _release_file_lock(conn, project_id, task_id, verbose)

        # 更新後のタスクを取得
        updated = fetch_one(
            conn,
            "SELECT * FROM tasks WHERE id = ? AND project_id = ?",
            (task_id, project_id)
        )

        result = row_to_dict(updated)

        if verbose:
            print(f"[INFO] Task {task_id} status reset to QUEUED", file=sys.stderr)

    return result


def _release_file_lock(
    conn,
    project_id: str,
    task_id: str,
    verbose: bool = False
) -> None:
    """
    タスクに関連するファイルロックを解放

    Args:
        conn: データベース接続
        project_id: プロジェクトID
        task_id: タスクID
        verbose: 詳細ログ出力
    """
    # file_locks テーブルが存在するか確認
    table_check = fetch_one(
        conn,
        "SELECT name FROM sqlite_master WHERE type='table' AND name='file_locks'",
        None
    )

    if not table_check:
        if verbose:
            print("[DEBUG] file_locks table does not exist", file=sys.stderr)
        return

    # このタスクが保持しているロックを解放
    execute_query(
        conn,
        """
        DELETE FROM file_locks
        WHERE locked_by LIKE ?
        """,
        (f"%{task_id}%",)
    )

    if verbose:
        print(f"[INFO] Released file locks for task {task_id}", file=sys.stderr)


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
        description="タスクステータスをQUEUEDに戻す（タイムアウト/停止リカバリ）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("task_id", help="タスクID")
    parser.add_argument("--reason", default="Timeout or manual stop", help="リセット理由")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    parser.add_argument("--verbose", "-v", action="store_true", help="詳細ログ出力")

    args = parser.parse_args()

    try:
        result = reset_task_status(
            args.project_id,
            args.task_id,
            reason=args.reason,
            verbose=args.verbose
        )

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"タスクステータスをリセットしました: {result['id']}")
            print(f"  ステータス: {result['status']}")
            print(f"  理由: {args.reason}")

        sys.exit(0)

    except (ValidationError, TransitionError, DatabaseError) as e:
        error_msg = f"エラー: {e}"
        if args.json:
            print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        else:
            print(error_msg, file=sys.stderr)
        sys.exit(1)

    except Exception as e:
        error_msg = f"予期しないエラー: {e}"
        if args.json:
            print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        else:
            print(error_msg, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
