#!/usr/bin/env python3
"""
AI PM Framework - REJECTEDタスク復帰スクリプト

REJECTEDステータスのタスクをQUEUEDに戻し、reject_countをリセットする。

Usage:
    python backend/task/recover_rejected.py PROJECT_NAME TASK_ID [options]

Options:
    --json          JSON形式で出力
    --reason        復帰理由（任意）

Example:
    python backend/task/recover_rejected.py ai_pm_manager TASK_717
    python backend/task/recover_rejected.py ai_pm_manager TASK_717 --reason "問題修正完了"
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# パス設定
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


class RecoverRejectedError(Exception):
    """REJECTED復帰エラー"""
    pass


def recover_rejected_task(
    project_id: str,
    task_id: str,
    *,
    role: str = "PM",
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """
    REJECTEDタスクをQUEUEDに復帰し、reject_countをリセット

    Args:
        project_id: プロジェクトID
        task_id: タスクID
        role: 操作者の役割（PM/System）
        reason: 復帰理由

    Returns:
        復帰結果の辞書

    Raises:
        ValidationError: 入力検証エラー
        TransitionError: 状態遷移エラー
        RecoverRejectedError: 復帰処理エラー
    """
    # 入力検証
    validate_project_name(project_id)
    validate_task_id(task_id)

    # TASK_XXX 形式に正規化
    if not task_id.startswith("TASK_"):
        task_id = f"TASK_{task_id}"

    if role not in ("PM", "System"):
        raise ValidationError(f"無効な役割: {role}（PM または System）", "role", role)

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
            """
            SELECT *
            FROM tasks
            WHERE id = ? AND project_id = ?
            """,
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

        # REJECTEDステータスチェック
        if current_status != "REJECTED":
            raise RecoverRejectedError(
                f"タスクはREJECTEDステータスではありません: {current_status}"
            )

        # 状態遷移検証（REJECTED → QUEUED）
        validate_transition(conn, "task", current_status, "QUEUED", role)

        # ステータスをQUEUEDに更新、reject_countをリセット
        execute_query(
            conn,
            """
            UPDATE tasks
            SET status = 'QUEUED',
                reject_count = 0,
                updated_at = ?
            WHERE id = ? AND project_id = ?
            """,
            (datetime.now().isoformat(), task_id, project_id)
        )

        # 状態遷移履歴を記録
        changed_by = f"{role} (recover_rejected)"
        record_transition(
            conn,
            "task",
            task_id,
            current_status,
            "QUEUED",
            changed_by,
            reason or "REJECTEDタスクの手動復帰（reject_count リセット）"
        )

        # 更新後のタスクを取得
        updated = fetch_one(
            conn,
            "SELECT * FROM tasks WHERE id = ? AND project_id = ?",
            (task_id, project_id)
        )

        result = {
            "success": True,
            "task_id": task_id,
            "project_id": project_id,
            "previous_status": current_status,
            "new_status": "QUEUED",
            "reject_count_before": current_dict.get("reject_count", 0),
            "reject_count_after": 0,
            "task": row_to_dict(updated),
        }

        return result


def main():
    """CLI エントリーポイント"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
        setup_utf8_output()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(
        description="REJECTEDタスクをQUEUEDに復帰",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("task_id", help="タスクID（例: 717 または TASK_717）")
    parser.add_argument("--reason", help="復帰理由")
    parser.add_argument("--role", default="PM", help="操作者の役割（PM/System、デフォルト: PM）")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    try:
        result = recover_rejected_task(
            args.project_id,
            args.task_id,
            role=args.role,
            reason=args.reason,
        )

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"✓ タスクを復帰しました: {result['task_id']}")
            print(f"  プロジェクト: {result['project_id']}")
            print(f"  ステータス: {result['previous_status']} → {result['new_status']}")
            print(f"  reject_count: {result['reject_count_before']} → {result['reject_count_after']}")

    except (ValidationError, TransitionError, RecoverRejectedError, DatabaseError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
