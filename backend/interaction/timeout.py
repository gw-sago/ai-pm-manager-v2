#!/usr/bin/env python3
"""
AI PM Framework - タイムアウト・エスカレーション処理

一定時間回答がないInteractionをTIMEOUT/ESCALATEDに更新

Usage:
    # 定期実行（cron等から）
    python backend/interaction/timeout.py --check

    # 特定プロジェクトのみ
    python backend/interaction/timeout.py --check --project AI_PM_PJ

    # ドライラン（実際には更新しない）
    python backend/interaction/timeout.py --check --dry-run

Options:
    --check             タイムアウトチェック実行
    --project           プロジェクトIDでフィルタ
    --timeout-minutes   タイムアウト時間（デフォルト: 1440分=24時間）
    --escalate          タイムアウト時にタスクをESCALATEDに
    --dry-run           実際には更新しない
    --json              JSON形式で出力
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

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
    row_to_dict,
    rows_to_dicts,
    DatabaseError,
)
from utils.transition import (
    record_transition,
    TransitionError,
)


# デフォルトタイムアウト（分）
DEFAULT_TIMEOUT_MINUTES = 1440  # 24時間


@dataclass
class TimeoutCheckResult:
    """タイムアウトチェック結果"""
    success: bool = False
    checked_count: int = 0
    timed_out_count: int = 0
    escalated_count: int = 0
    timed_out_interactions: List[Dict[str, Any]] = field(default_factory=list)
    escalated_tasks: List[Dict[str, Any]] = field(default_factory=list)
    message: str = ""
    error: Optional[str] = None


def get_pending_interactions(
    conn,
    project_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    PENDING状態のInteractionを取得

    Args:
        conn: データベース接続
        project_id: プロジェクトID（フィルタ）

    Returns:
        PENDING Interaction一覧
    """
    query = """
        SELECT
            i.*,
            t.status as task_status,
            t.title as task_title
        FROM interactions i
        LEFT JOIN tasks t ON i.task_id = t.id AND i.project_id = t.project_id
        WHERE i.status = 'PENDING'
    """
    params = []

    if project_id:
        query += " AND i.project_id = ?"
        params.append(project_id)

    query += " ORDER BY i.created_at ASC"

    rows = fetch_all(conn, query, tuple(params))
    return rows_to_dicts(rows)


def is_timed_out(
    interaction: Dict[str, Any],
    timeout_minutes: int = DEFAULT_TIMEOUT_MINUTES
) -> bool:
    """
    Interactionがタイムアウトしているかチェック

    Args:
        interaction: Interactionデータ
        timeout_minutes: タイムアウト時間（分）

    Returns:
        タイムアウトしている場合True
    """
    # timeout_at が設定されている場合はそれを使用
    timeout_at = interaction.get("timeout_at")
    if timeout_at:
        try:
            timeout_dt = datetime.fromisoformat(timeout_at)
            return datetime.now() > timeout_dt
        except (ValueError, TypeError):
            pass

    # created_at からタイムアウト判定
    created_at = interaction.get("created_at")
    if created_at:
        try:
            created_dt = datetime.fromisoformat(created_at)
            timeout_dt = created_dt + timedelta(minutes=timeout_minutes)
            return datetime.now() > timeout_dt
        except (ValueError, TypeError):
            pass

    return False


def process_timeout(
    conn,
    interaction: Dict[str, Any],
    *,
    escalate_task: bool = False,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    タイムアウト処理を実行

    Args:
        conn: データベース接続
        interaction: Interactionデータ
        escalate_task: タスクもESCALATEDに更新
        dry_run: 実際には更新しない

    Returns:
        処理結果
    """
    interaction_id = interaction.get("id")
    task_id = interaction.get("task_id")
    project_id = interaction.get("project_id")

    result = {
        "interaction_id": interaction_id,
        "task_id": task_id,
        "project_id": project_id,
        "action": "timeout",
        "task_escalated": False,
    }

    if dry_run:
        result["dry_run"] = True
        return result

    now = datetime.now().isoformat()

    # Interaction を TIMEOUT に更新
    execute_query(
        conn,
        """
        UPDATE interactions
        SET status = 'TIMEOUT', updated_at = ?
        WHERE id = ?
        """,
        (now, interaction_id)
    )

    # 変更履歴を記録
    record_transition(
        conn,
        "interaction",
        interaction_id,
        "PENDING",
        "TIMEOUT",
        "System",
        "タイムアウト（回答期限超過）",
        project_id=project_id,
    )

    # タスクのエスカレーション
    if escalate_task:
        task_status = interaction.get("task_status")
        if task_status == "WAITING_INPUT":
            execute_query(
                conn,
                """
                UPDATE tasks
                SET status = 'ESCALATED', updated_at = ?
                WHERE id = ? AND project_id = ?
                """,
                (now, task_id, project_id)
            )

            record_transition(
                conn,
                "task",
                task_id,
                "WAITING_INPUT",
                "ESCALATED",
                "System",
                f"対話タイムアウトによるエスカレーション: {interaction_id}",
                project_id=project_id,
            )

            result["task_escalated"] = True

    return result


def check_timeouts(
    project_id: Optional[str] = None,
    *,
    timeout_minutes: int = DEFAULT_TIMEOUT_MINUTES,
    escalate: bool = False,
    dry_run: bool = False,
    db_path: Optional[Path] = None,
) -> TimeoutCheckResult:
    """
    タイムアウトチェックを実行

    Args:
        project_id: プロジェクトID（フィルタ）
        timeout_minutes: タイムアウト時間（分）
        escalate: タスクもESCALATEDに更新
        dry_run: 実際には更新しない
        db_path: データベースパス（テスト用）

    Returns:
        TimeoutCheckResult: チェック結果
    """
    result = TimeoutCheckResult()

    try:
        with transaction(db_path=db_path) as conn:
            # PENDING Interactionを取得
            pending = get_pending_interactions(conn, project_id)
            result.checked_count = len(pending)

            # タイムアウトチェック
            for interaction in pending:
                if is_timed_out(interaction, timeout_minutes):
                    # タイムアウト処理
                    process_result = process_timeout(
                        conn,
                        interaction,
                        escalate_task=escalate,
                        dry_run=dry_run
                    )

                    result.timed_out_count += 1
                    result.timed_out_interactions.append({
                        "id": interaction.get("id"),
                        "task_id": interaction.get("task_id"),
                        "project_id": interaction.get("project_id"),
                        "question": interaction.get("question_text", "")[:50],
                        "created_at": interaction.get("created_at"),
                    })

                    if process_result.get("task_escalated"):
                        result.escalated_count += 1
                        result.escalated_tasks.append({
                            "task_id": interaction.get("task_id"),
                            "project_id": interaction.get("project_id"),
                            "title": interaction.get("task_title"),
                        })

            if dry_run:
                result.message = f"[ドライラン] チェック: {result.checked_count}件, タイムアウト: {result.timed_out_count}件"
            else:
                result.message = f"チェック: {result.checked_count}件, タイムアウト更新: {result.timed_out_count}件, エスカレーション: {result.escalated_count}件"

            result.success = True

    except DatabaseError as e:
        result.error = f"データベースエラー: {e}"
    except Exception as e:
        result.error = f"予期しないエラー: {e}"

    return result


def cancel_interaction(
    interaction_id: str,
    *,
    reason: str = "管理者によるキャンセル",
    resume_task: bool = True,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Interactionをキャンセル

    Args:
        interaction_id: Interaction ID
        reason: キャンセル理由
        resume_task: タスクをIN_PROGRESSに戻す
        db_path: データベースパス（テスト用）

    Returns:
        処理結果
    """
    try:
        with transaction(db_path=db_path) as conn:
            # Interaction取得
            interaction = fetch_one(
                conn,
                "SELECT * FROM interactions WHERE id = ?",
                (interaction_id,)
            )
            if not interaction:
                return {"success": False, "error": f"Interactionが見つかりません: {interaction_id}"}

            interaction = row_to_dict(interaction)
            if interaction["status"] != "PENDING":
                return {"success": False, "error": f"PENDING以外はキャンセルできません: {interaction['status']}"}

            now = datetime.now().isoformat()

            # Interactionをキャンセル
            execute_query(
                conn,
                """
                UPDATE interactions
                SET status = 'CANCELLED', updated_at = ?
                WHERE id = ?
                """,
                (now, interaction_id)
            )

            record_transition(
                conn,
                "interaction",
                interaction_id,
                "PENDING",
                "CANCELLED",
                "PM",
                reason,
                project_id=interaction.get("project_id"),
            )

            # タスクを再開
            task_resumed = False
            if resume_task:
                task_id = interaction.get("task_id")
                project_id = interaction.get("project_id")

                # 現在のタスク状態を確認
                task = fetch_one(
                    conn,
                    "SELECT status FROM tasks WHERE id = ? AND project_id = ?",
                    (task_id, project_id)
                )
                if task and task["status"] == "WAITING_INPUT":
                    execute_query(
                        conn,
                        """
                        UPDATE tasks
                        SET status = 'IN_PROGRESS', updated_at = ?
                        WHERE id = ? AND project_id = ?
                        """,
                        (now, task_id, project_id)
                    )

                    record_transition(
                        conn,
                        "task",
                        task_id,
                        "WAITING_INPUT",
                        "IN_PROGRESS",
                        "PM",
                        f"Interactionキャンセルによる再開: {interaction_id}",
                        project_id=project_id,
                    )
                    task_resumed = True

            return {
                "success": True,
                "interaction_id": interaction_id,
                "task_id": interaction.get("task_id"),
                "task_resumed": task_resumed,
                "message": f"Interactionをキャンセルしました: {interaction_id}"
            }

    except Exception as e:
        return {"success": False, "error": str(e)}


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
        description="タイムアウト・エスカレーション処理",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # タイムアウトチェック
  python timeout.py --check

  # ドライラン
  python timeout.py --check --dry-run

  # エスカレーション付き
  python timeout.py --check --escalate

  # 特定プロジェクト
  python timeout.py --check --project AI_PM_PJ

  # Interactionをキャンセル
  python timeout.py --cancel INT_00001
"""
    )

    parser.add_argument(
        "--check",
        action="store_true",
        help="タイムアウトチェック実行"
    )
    parser.add_argument(
        "--cancel",
        metavar="INTERACTION_ID",
        help="Interactionをキャンセル"
    )
    parser.add_argument(
        "--project", "-p",
        help="プロジェクトIDでフィルタ"
    )
    parser.add_argument(
        "--timeout-minutes", "-t",
        type=int,
        default=DEFAULT_TIMEOUT_MINUTES,
        help=f"タイムアウト時間（分、デフォルト: {DEFAULT_TIMEOUT_MINUTES}）"
    )
    parser.add_argument(
        "--escalate",
        action="store_true",
        help="タイムアウト時にタスクをESCALATEDに"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実際には更新しない"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )

    args = parser.parse_args()

    if args.check:
        result = check_timeouts(
            project_id=args.project,
            timeout_minutes=args.timeout_minutes,
            escalate=args.escalate,
            dry_run=args.dry_run,
        )

        if args.json:
            output = {
                "success": result.success,
                "checked_count": result.checked_count,
                "timed_out_count": result.timed_out_count,
                "escalated_count": result.escalated_count,
                "timed_out_interactions": result.timed_out_interactions,
                "escalated_tasks": result.escalated_tasks,
                "message": result.message,
                "error": result.error,
            }
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            if result.success:
                print(f"[OK] {result.message}")
                if result.timed_out_interactions:
                    print("\n■ タイムアウト Interaction:")
                    for i in result.timed_out_interactions:
                        print(f"  - {i['id']} ({i['project_id']}/{i['task_id']}): {i['question']}...")
                if result.escalated_tasks:
                    print("\n■ エスカレーション タスク:")
                    for t in result.escalated_tasks:
                        print(f"  - {t['task_id']}: {t['title']}")
            else:
                print(f"[ERROR] {result.error}", file=sys.stderr)
                sys.exit(1)

    elif args.cancel:
        result = cancel_interaction(
            args.cancel,
            resume_task=True,
        )

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            if result.get("success"):
                print(f"[OK] {result.get('message')}")
                if result.get("task_resumed"):
                    print(f"  タスク {result.get('task_id')} を IN_PROGRESS に戻しました")
            else:
                print(f"[ERROR] {result.get('error')}", file=sys.stderr)
                sys.exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
