"""
AI PM Framework - レビューキュー追加スクリプト

⚠️ DEPRECATED: このファイルは非推奨です。
ORDER_145でreview_queueテーブルが廃止され、reviewed_at方式に移行しました。
process_review.pyはreview_queueを使用せず、tasks.reviewed_atでレビュー管理を行います。

このファイルは後方互換性のためにのみ残されており、実際には使用されていません。
"""

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

# パス設定（パッケージとして実行される場合と直接実行される場合の両方に対応）
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import (
    get_connection,
    transaction,
    execute_query,
    fetch_one,
    DatabaseError,
)
from utils.transition import (
    validate_transition,
    record_transition,
    TransitionError,
)


@dataclass
class AddToQueueResult:
    """レビューキュー追加結果"""
    success: bool
    queue_id: Optional[int] = None
    task_id: str = ""
    priority: str = "P1"
    message: str = ""
    error: Optional[str] = None


def determine_priority(
    conn,
    task_id: str,
    project_id: str,
    is_resubmit: bool = False,
    explicit_priority: Optional[str] = None,
) -> str:
    """
    優先度を決定

    Args:
        conn: データベース接続
        task_id: タスクID
        project_id: プロジェクトID
        is_resubmit: 再提出かどうか（差し戻し後の再提出）
        explicit_priority: 明示的に指定された優先度

    Returns:
        str: 優先度（P0/P1/P2）

    Priority Rules:
        - P0: 差し戻し再提出（最優先）
        - P1: 通常提出（FIFO）
        - P2: 明示的に低優先指定
    """
    # 明示的に指定された場合はそれを使用
    if explicit_priority and explicit_priority in ("P0", "P1", "P2"):
        return explicit_priority

    # 再提出の場合は P0
    if is_resubmit:
        return "P0"

    # タスクのステータスを確認して判断（複合キー対応）
    row = fetch_one(
        conn,
        "SELECT status FROM tasks WHERE id = ? AND project_id = ?",
        (task_id, project_id)
    )

    if row and row["status"] == "REWORK":
        # REWORK から DONE への遷移 → 差し戻し再提出
        return "P0"

    # デフォルトは P1
    return "P1"


def add_to_queue(
    project_name: str,
    task_id: str,
    priority: Optional[str] = None,
    is_resubmit: bool = False,
    comment: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> AddToQueueResult:
    """
    レビューキューにタスクを追加

    Args:
        project_name: プロジェクト名
        task_id: タスクID（TASK_XXX形式）
        priority: 優先度（P0/P1/P2）、指定しない場合は自動決定
        is_resubmit: 再提出フラグ（差し戻し後の再提出）
        comment: コメント（再提出の場合は「再提出」等）
        db_path: データベースパス（テスト用）

    Returns:
        AddToQueueResult: 追加結果

    Workflow:
        1. タスク存在確認
        2. 優先度決定（P0: 差し戻し再提出、P1: 通常、P2: 低優先）
        3. レビューキューにINSERT
        4. タスクステータスをDONEに更新
        5. 変更履歴を記録
    """
    try:
        with transaction(db_path=db_path) as conn:
            # 1. タスク存在確認（複合キー対応）
            task = fetch_one(
                conn,
                """
                SELECT t.id, t.status, t.title, t.project_id
                FROM tasks t
                JOIN projects p ON t.project_id = p.id
                WHERE t.id = ? AND t.project_id = ?
                """,
                (task_id, project_name)
            )

            if not task:
                return AddToQueueResult(
                    success=False,
                    task_id=task_id,
                    error=f"タスクが見つかりません: {task_id} (プロジェクト: {project_name})"
                )

            current_status = task["status"]

            # 重複追加チェック（ステータスに関わらず実施）
            # PENDING または IN_REVIEW の既存エントリがあれば重複とみなす
            existing = fetch_one(
                conn,
                """
                SELECT id, status FROM review_queue
                WHERE task_id = ? AND project_id = ? AND status IN ('PENDING', 'IN_REVIEW')
                """,
                (task_id, project_name)
            )
            if existing:
                existing_status = existing["status"]
                return AddToQueueResult(
                    success=False,
                    task_id=task_id,
                    error=f"タスクは既にレビューキューにあります: {task_id} (現在のキューステータス: {existing_status})"
                )

            # 2. 優先度決定（複合キー対応）
            final_priority = determine_priority(
                conn, task_id, project_name, is_resubmit, priority
            )

            # 再提出判定の追加ロジック
            if current_status == "REWORK":
                is_resubmit = True
                if final_priority != "P0":
                    final_priority = "P0"

            # 3. 状態遷移の検証（IN_PROGRESS/REWORK → DONE）
            # DONEへの遷移が許可されているか確認
            if current_status not in ("DONE",):  # 既にDONEでなければ遷移
                validate_transition(
                    conn, "task", current_status, "DONE", "Worker"
                )

            # 4. レビューキューにINSERT
            final_comment = comment
            if is_resubmit and not final_comment:
                final_comment = "再提出"

            # project_idを取得（task情報から）
            project_id = task["project_id"]

            cursor = execute_query(
                conn,
                """
                INSERT INTO review_queue (task_id, project_id, status, priority, comment)
                VALUES (?, ?, 'PENDING', ?, ?)
                """,
                (task_id, project_id, final_priority, final_comment)
            )
            queue_id = cursor.lastrowid

            # 5. タスクステータスをDONEに更新（まだDONEでなければ）（複合キー対応）
            if current_status != "DONE":
                execute_query(
                    conn,
                    "UPDATE tasks SET status = 'DONE' WHERE id = ? AND project_id = ?",
                    (task_id, project_id)
                )

                # 変更履歴を記録
                record_transition(
                    conn,
                    "task",
                    task_id,
                    current_status,
                    "DONE",
                    "Worker",
                    f"レビューキューに追加 (優先度: {final_priority})"
                )

            # レビューキュー追加の変更履歴
            record_transition(
                conn,
                "review",
                str(queue_id),
                None,
                "PENDING",
                "Worker",
                f"タスク {task_id} をレビューキューに追加"
            )

            return AddToQueueResult(
                success=True,
                queue_id=queue_id,
                task_id=task_id,
                priority=final_priority,
                message=f"レビューキューに追加しました (ID: {queue_id}, 優先度: {final_priority})"
            )

    except TransitionError as e:
        return AddToQueueResult(
            success=False,
            task_id=task_id,
            error=f"状態遷移エラー: {e}"
        )
    except DatabaseError as e:
        return AddToQueueResult(
            success=False,
            task_id=task_id,
            error=f"データベースエラー: {e}"
        )
    except Exception as e:
        return AddToQueueResult(
            success=False,
            task_id=task_id,
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
        description="レビューキューにタスクを追加",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 通常追加（P1優先度）
  python add.py AI_PM_PJ TASK_188

  # 高優先度で追加（差し戻し再提出）
  python add.py AI_PM_PJ TASK_188 --priority P0 --resubmit

  # コメント付きで追加
  python add.py AI_PM_PJ TASK_188 --comment "修正完了"
"""
    )

    parser.add_argument(
        "project_name",
        help="プロジェクト名 (例: AI_PM_PJ)"
    )
    parser.add_argument(
        "task_id",
        help="タスクID (例: TASK_188)"
    )
    parser.add_argument(
        "--priority", "-p",
        choices=["P0", "P1", "P2"],
        help="優先度 (P0: 最優先, P1: 通常, P2: 低優先)"
    )
    parser.add_argument(
        "--resubmit", "-r",
        action="store_true",
        help="差し戻し後の再提出フラグ"
    )
    parser.add_argument(
        "--comment", "-c",
        help="コメント"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )

    args = parser.parse_args()

    result = add_to_queue(
        project_name=args.project_name,
        task_id=args.task_id,
        priority=args.priority,
        is_resubmit=args.resubmit,
        comment=args.comment,
    )

    if args.json:
        import json
        output = {
            "success": result.success,
            "queue_id": result.queue_id,
            "task_id": result.task_id,
            "priority": result.priority,
            "message": result.message,
            "error": result.error,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        if result.success:
            print(f"[OK] {result.message}")
        else:
            print(f"[ERROR] {result.error}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
