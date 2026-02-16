"""
AI PM Framework - レビュー状態更新スクリプト

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
    DatabaseError,
)
from utils.transition import (
    validate_transition,
    record_transition,
    TransitionError,
)

# task/update.pyから依存タスクブロック解除関数をインポート
try:
    from task.update import _check_unblock_dependent_tasks
except ImportError:
    _check_unblock_dependent_tasks = None


@dataclass
class UpdateReviewResult:
    """レビュー状態更新結果"""
    success: bool
    queue_id: Optional[int] = None
    task_id: str = ""
    old_review_status: str = ""
    new_review_status: str = ""
    old_task_status: str = ""
    new_task_status: str = ""
    message: str = ""
    error: Optional[str] = None


# レビューステータスとタスクステータスの対応
REVIEW_TASK_STATUS_MAP = {
    "APPROVED": "COMPLETED",  # 承認 → タスク完了
    "REJECTED": "REWORK",     # 差し戻し → 再作業
    "ESCALATED": "ESCALATED", # エスカレーション → タスクもエスカレーション
}


def _check_and_complete_order(conn, task_id: str, project_name: str) -> Optional[str]:
    """
    タスク完了後、ORDER全体の完了をチェックし、全タスク完了なら ORDER を COMPLETED に更新

    Args:
        conn: データベース接続
        task_id: 完了したタスクID
        project_name: プロジェクト名

    Returns:
        完了したORDER IDまたはNone
    """
    # タスクの所属ORDERを取得
    task = fetch_one(
        conn,
        "SELECT order_id FROM tasks WHERE id = ? AND project_id = ?",
        (task_id, project_name)
    )

    if not task or not task["order_id"]:
        return None

    order_id = task["order_id"]

    # ORDER配下の全タスクステータスを確認
    incomplete_tasks = fetch_one(
        conn,
        """
        SELECT COUNT(*) as count
        FROM tasks
        WHERE order_id = ? AND project_id = ? AND status != 'COMPLETED'
        """,
        (order_id, project_name)
    )

    if incomplete_tasks and incomplete_tasks["count"] > 0:
        # まだ未完了タスクがある
        return None

    # 全タスク完了 → ORDER を COMPLETED に更新
    # まずORDERの現在ステータスを確認
    order = fetch_one(
        conn,
        "SELECT status FROM orders WHERE id = ? AND project_id = ?",
        (order_id, project_name)
    )

    if not order:
        return None

    if order["status"] == "COMPLETED":
        # 既に完了済み
        return None

    # ORDER を COMPLETED に更新
    execute_query(
        conn,
        """
        UPDATE orders
        SET status = 'COMPLETED', completed_at = CURRENT_TIMESTAMP
        WHERE id = ? AND project_id = ?
        """,
        (order_id, project_name)
    )

    # 状態遷移履歴を記録
    record_transition(
        conn,
        "order",
        order_id,
        order["status"],
        "COMPLETED",
        "PM",
        "全タスク完了によるORDER自動完了"
    )

    return order_id


def update_review_status(
    project_name: str,
    task_id: str,
    new_status: str,
    reviewer: Optional[str] = None,
    comment: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> UpdateReviewResult:
    """
    レビュー状態を更新

    Args:
        project_name: プロジェクト名
        task_id: タスクID
        new_status: 新しいレビューステータス（PENDING/IN_REVIEW/APPROVED/REJECTED）
        reviewer: レビュアー名（通常は "PM"）
        comment: レビューコメント
        db_path: データベースパス（テスト用）

    Returns:
        UpdateReviewResult: 更新結果

    State Transitions:
        - PENDING → IN_REVIEW: PM がレビュー開始
        - IN_REVIEW → APPROVED: 承認（タスク→COMPLETED、キューから削除）
        - IN_REVIEW → REJECTED: 差し戻し（タスク→REWORK）
        - IN_REVIEW → ESCALATED: エスカレーション（タスク→ESCALATED）
        - ESCALATED → PENDING: エスカレーション解決後の再レビュー
        - REJECTED → PENDING: Worker が再提出（別処理、add.py で対応）
    """
    try:
        with transaction(db_path=db_path) as conn:
            # 1. レビューキューから該当エントリを取得（複合キー対応）
            review_entry = fetch_one(
                conn,
                """
                SELECT rq.id, rq.task_id, rq.project_id, rq.status, rq.reviewer, rq.priority
                FROM review_queue rq
                WHERE rq.task_id = ?
                  AND rq.project_id = ?
                  AND rq.status IN ('PENDING', 'IN_REVIEW', 'REJECTED', 'ESCALATED')
                ORDER BY rq.submitted_at DESC
                LIMIT 1
                """,
                (task_id, project_name)
            )

            if not review_entry:
                return UpdateReviewResult(
                    success=False,
                    task_id=task_id,
                    error=f"レビューキューにエントリがありません: {task_id}"
                )

            queue_id = review_entry["id"]
            current_review_status = review_entry["status"]

            # 2. タスクの現在ステータスを取得（複合キー対応）
            task = fetch_one(
                conn,
                "SELECT status FROM tasks WHERE id = ? AND project_id = ?",
                (task_id, project_name)
            )

            if not task:
                return UpdateReviewResult(
                    success=False,
                    task_id=task_id,
                    error=f"タスクが見つかりません: {task_id}"
                )

            current_task_status = task["status"]

            # 3. レビュー状態遷移の検証
            validate_transition(
                conn, "review", current_review_status, new_status, "PM"
            )

            # 4. レビューキューを更新
            update_fields = ["status = ?"]
            update_params = [new_status]

            if reviewer:
                update_fields.append("reviewer = ?")
                update_params.append(reviewer)

            if comment:
                update_fields.append("comment = ?")
                update_params.append(comment)

            if new_status in ("APPROVED", "REJECTED"):
                update_fields.append("reviewed_at = CURRENT_TIMESTAMP")

            update_params.append(queue_id)

            execute_query(
                conn,
                f"UPDATE review_queue SET {', '.join(update_fields)} WHERE id = ?",
                tuple(update_params)
            )

            # レビュー状態変更の履歴記録
            record_transition(
                conn,
                "review",
                str(queue_id),
                current_review_status,
                new_status,
                reviewer or "PM",
                comment
            )

            # 5. タスクステータスの連動更新
            new_task_status = current_task_status

            if new_status == "APPROVED":
                # 承認 → タスクをCOMPLETEDに更新（複合キー対応）
                validate_transition(
                    conn, "task", current_task_status, "COMPLETED", "PM"
                )
                execute_query(
                    conn,
                    """
                    UPDATE tasks
                    SET status = 'COMPLETED', completed_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND project_id = ?
                    """,
                    (task_id, project_name)
                )
                new_task_status = "COMPLETED"

                # タスク状態変更の履歴記録
                record_transition(
                    conn,
                    "task",
                    task_id,
                    current_task_status,
                    "COMPLETED",
                    reviewer or "PM",
                    "レビュー承認"
                )

                # 依存タスクのブロック解除をチェック
                if _check_unblock_dependent_tasks:
                    unblocked = _check_unblock_dependent_tasks(conn, task_id, project_name)
                    if unblocked:
                        print(f"[INFO] ブロック解除されたタスク: {', '.join(unblocked)}")

                # ORDER完了判定: 全タスクがCOMPLETEDならORDERもCOMPLETED
                order_completed = _check_and_complete_order(conn, task_id, project_name)
                if order_completed:
                    print(f"[INFO] ORDER完了: {order_completed}")

                # APPROVED の場合、レビューキューから論理削除（または保持）
                # 今回は履歴として保持

            elif new_status == "REJECTED":
                # 差し戻し → タスクをREWORKに更新（複合キー対応）
                # NOTE: reject_count による REJECTED 遷移は process_review.py の
                # _step_auto_rework() で REWORK → REJECTED として処理する。
                # ここでは常に DONE → REWORK に遷移させる（DONE → REJECTED は
                # status_transitions で許可されていないため）。
                validate_transition(
                    conn, "task", current_task_status, "REWORK", "PM"
                )
                execute_query(
                    conn,
                    "UPDATE tasks SET status = 'REWORK' WHERE id = ? AND project_id = ?",
                    (task_id, project_name)
                )
                new_task_status = "REWORK"

                # reject_count をインクリメント
                execute_query(
                    conn,
                    """
                    UPDATE tasks
                    SET reject_count = COALESCE(reject_count, 0) + 1
                    WHERE id = ? AND project_id = ?
                    """,
                    (task_id, project_name)
                )

                # タスク状態変更の履歴記録
                record_transition(
                    conn,
                    "task",
                    task_id,
                    current_task_status,
                    "REWORK",
                    reviewer or "PM",
                    comment or "レビュー差し戻し"
                )

            elif new_status == "ESCALATED":
                # エスカレーション → タスクをESCALATEDに更新（複合キー対応）
                validate_transition(
                    conn, "task", current_task_status, "ESCALATED", "PM"
                )
                execute_query(
                    conn,
                    "UPDATE tasks SET status = 'ESCALATED' WHERE id = ? AND project_id = ?",
                    (task_id, project_name)
                )
                new_task_status = "ESCALATED"

                # タスク状態変更の履歴記録
                record_transition(
                    conn,
                    "task",
                    task_id,
                    current_task_status,
                    "ESCALATED",
                    reviewer or "PM",
                    comment or "レビューエスカレーション"
                )

            return UpdateReviewResult(
                success=True,
                queue_id=queue_id,
                task_id=task_id,
                old_review_status=current_review_status,
                new_review_status=new_status,
                old_task_status=current_task_status,
                new_task_status=new_task_status,
                message=f"レビュー状態を更新しました: {current_review_status} → {new_status}"
            )

    except TransitionError as e:
        return UpdateReviewResult(
            success=False,
            task_id=task_id,
            error=f"状態遷移エラー: {e}"
        )
    except DatabaseError as e:
        return UpdateReviewResult(
            success=False,
            task_id=task_id,
            error=f"データベースエラー: {e}"
        )
    except Exception as e:
        return UpdateReviewResult(
            success=False,
            task_id=task_id,
            error=f"予期しないエラー: {e}"
        )


def start_review(
    project_name: str,
    task_id: str,
    reviewer: str = "PM",
    db_path: Optional[Path] = None,
) -> UpdateReviewResult:
    """
    レビューを開始する（PENDING → IN_REVIEW）

    Args:
        project_name: プロジェクト名
        task_id: タスクID
        reviewer: レビュアー名
        db_path: データベースパス

    Returns:
        UpdateReviewResult: 更新結果
    """
    return update_review_status(
        project_name=project_name,
        task_id=task_id,
        new_status="IN_REVIEW",
        reviewer=reviewer,
        db_path=db_path,
    )


def approve_review(
    project_name: str,
    task_id: str,
    reviewer: str = "PM",
    comment: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> UpdateReviewResult:
    """
    レビューを承認する（IN_REVIEW → APPROVED）

    Args:
        project_name: プロジェクト名
        task_id: タスクID
        reviewer: レビュアー名
        comment: 承認コメント
        db_path: データベースパス

    Returns:
        UpdateReviewResult: 更新結果
    """
    return update_review_status(
        project_name=project_name,
        task_id=task_id,
        new_status="APPROVED",
        reviewer=reviewer,
        comment=comment,
        db_path=db_path,
    )


def reject_review(
    project_name: str,
    task_id: str,
    reviewer: str = "PM",
    comment: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> UpdateReviewResult:
    """
    レビューを差し戻す（IN_REVIEW → REJECTED）

    Args:
        project_name: プロジェクト名
        task_id: タスクID
        reviewer: レビュアー名
        comment: 差し戻し理由
        db_path: データベースパス

    Returns:
        UpdateReviewResult: 更新結果
    """
    return update_review_status(
        project_name=project_name,
        task_id=task_id,
        new_status="REJECTED",
        reviewer=reviewer,
        comment=comment,
        db_path=db_path,
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
        description="レビュー状態を更新",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # レビュー開始
  python update.py AI_PM_PJ TASK_188 IN_REVIEW --reviewer PM

  # レビュー承認
  python update.py AI_PM_PJ TASK_188 APPROVED --reviewer PM --comment "完了条件達成"

  # レビュー差し戻し
  python update.py AI_PM_PJ TASK_188 REJECTED --reviewer PM --comment "テスト不足"

状態遷移:
  PENDING → IN_REVIEW   : PMがレビュー開始
  IN_REVIEW → APPROVED  : 承認（タスク→COMPLETED）
  IN_REVIEW → REJECTED  : 差し戻し（タスク→REWORK）
  IN_REVIEW → ESCALATED : エスカレーション（タスク→ESCALATED）
  ESCALATED → PENDING   : エスカレーション解決後の再レビュー
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
        "new_status",
        choices=["IN_REVIEW", "APPROVED", "REJECTED", "ESCALATED"],
        help="新しいレビューステータス"
    )
    parser.add_argument(
        "--reviewer", "-r",
        default="PM",
        help="レビュアー名 (デフォルト: PM)"
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

    result = update_review_status(
        project_name=args.project_name,
        task_id=args.task_id,
        new_status=args.new_status,
        reviewer=args.reviewer,
        comment=args.comment,
    )

    if args.json:
        import json
        output = {
            "success": result.success,
            "queue_id": result.queue_id,
            "task_id": result.task_id,
            "old_review_status": result.old_review_status,
            "new_review_status": result.new_review_status,
            "old_task_status": result.old_task_status,
            "new_task_status": result.new_task_status,
            "message": result.message,
            "error": result.error,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        if result.success:
            print(f"[OK] {result.message}")
            if result.old_task_status != result.new_task_status:
                print(f"     タスク状態: {result.old_task_status} → {result.new_task_status}")
        else:
            print(f"[ERROR] {result.error}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
