#!/usr/bin/env python3
"""
AI PM Framework - タスク再開スクリプト

ユーザー回答後にタスクを再開する

Usage:
    python backend/interaction/resume.py INTERACTION_ID [options]
    python backend/interaction/resume.py --task TASK_ID --project PROJECT_ID [options]

Options:
    --interaction-id    Interaction ID（必須、または --task/--project）
    --task              タスクID（WAITING_INPUT状態のタスクを指定）
    --project           プロジェクトID
    --skip-validation   回答済み検証をスキップ
    --json              JSON形式で出力

Example:
    python backend/interaction/resume.py INT_00001
    python backend/interaction/resume.py --task TASK_123 --project AI_PM_PJ
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


@dataclass
class ResumeResult:
    """タスク再開結果"""
    success: bool = False
    task_id: str = ""
    project_id: str = ""
    previous_status: str = ""
    new_status: str = ""
    interaction_id: str = ""
    question_text: str = ""
    answer_text: str = ""
    context_for_resume: Dict[str, Any] = None
    message: str = ""
    error: Optional[str] = None

    def __post_init__(self):
        if self.context_for_resume is None:
            self.context_for_resume = {}


def get_pending_interactions_for_task(
    conn,
    task_id: str,
    project_id: str
) -> List[Dict[str, Any]]:
    """
    タスクに関連するANSWERED状態のInteractionを取得

    Args:
        conn: データベース接続
        task_id: タスクID
        project_id: プロジェクトID

    Returns:
        ANSWEREDのInteraction一覧
    """
    rows = fetch_all(
        conn,
        """
        SELECT * FROM interactions
        WHERE task_id = ? AND project_id = ? AND status = 'ANSWERED'
        ORDER BY answered_at DESC
        """,
        (task_id, project_id)
    )
    return rows_to_dicts(rows)


def get_interaction_with_task(
    conn,
    interaction_id: str
) -> Optional[Dict[str, Any]]:
    """
    Interactionとタスク情報を取得

    Args:
        conn: データベース接続
        interaction_id: Interaction ID

    Returns:
        Interaction + タスク情報
    """
    row = fetch_one(
        conn,
        """
        SELECT
            i.*,
            t.status as task_status,
            t.title as task_title,
            t.description as task_description,
            o.title as order_title
        FROM interactions i
        LEFT JOIN tasks t ON i.task_id = t.id AND i.project_id = t.project_id
        LEFT JOIN orders o ON t.order_id = o.id AND t.project_id = o.project_id
        WHERE i.id = ?
        """,
        (interaction_id,)
    )
    return row_to_dict(row) if row else None


def build_resume_context(
    interaction: Dict[str, Any],
    all_interactions: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    タスク再開用のコンテキストを構築

    Args:
        interaction: メインのInteraction
        all_interactions: 同じタスクの全Interaction

    Returns:
        再開用コンテキスト
    """
    context = {
        "task_id": interaction.get("task_id"),
        "project_id": interaction.get("project_id"),
        "session_id": interaction.get("session_id"),
        "latest_interaction": {
            "id": interaction.get("id"),
            "question": interaction.get("question_text"),
            "answer": interaction.get("answer_text"),
            "question_type": interaction.get("question_type"),
            "answered_at": interaction.get("answered_at"),
        },
        "task_info": {
            "title": interaction.get("task_title"),
            "description": interaction.get("task_description"),
            "order_title": interaction.get("order_title"),
        },
    }

    # 追加のコンテキスト（context_snapshot）があれば追加
    if interaction.get("context_snapshot"):
        try:
            snapshot = json.loads(interaction["context_snapshot"])
            context["original_context"] = snapshot
        except json.JSONDecodeError:
            pass

    # 過去のやり取り履歴を追加
    if all_interactions and len(all_interactions) > 1:
        context["interaction_history"] = [
            {
                "id": i.get("id"),
                "question": i.get("question_text"),
                "answer": i.get("answer_text"),
                "answered_at": i.get("answered_at"),
            }
            for i in all_interactions
        ]

    return context


def resume_task(
    interaction_id: Optional[str] = None,
    *,
    task_id: Optional[str] = None,
    project_id: Optional[str] = None,
    skip_validation: bool = False,
    db_path: Optional[Path] = None,
) -> ResumeResult:
    """
    タスクを再開

    ユーザー回答後、タスク状態をWAITING_INPUT → IN_PROGRESS に戻し、
    再開に必要なコンテキストを構築

    Args:
        interaction_id: Interaction ID（これか task_id+project_id のどちらか必須）
        task_id: タスクID
        project_id: プロジェクトID
        skip_validation: 回答済み検証をスキップ
        db_path: データベースパス（テスト用）

    Returns:
        ResumeResult: 再開結果（context_for_resumeに再開用コンテキストを含む）
    """
    result = ResumeResult()

    try:
        with transaction(db_path=db_path) as conn:
            # Interaction取得
            if interaction_id:
                interaction = get_interaction_with_task(conn, interaction_id)
                if not interaction:
                    return ResumeResult(
                        success=False,
                        error=f"Interactionが見つかりません: {interaction_id}"
                    )
                task_id = interaction.get("task_id")
                project_id = interaction.get("project_id")
            elif task_id and project_id:
                # タスクに関連するANSWERED Interactionを取得
                answered = get_pending_interactions_for_task(conn, task_id, project_id)
                if not answered:
                    if not skip_validation:
                        return ResumeResult(
                            success=False,
                            error=f"回答済みのInteractionがありません: {task_id}"
                        )
                    interaction = {}
                else:
                    interaction = answered[0]  # 最新の回答を使用
                    interaction_id = interaction.get("id")
            else:
                return ResumeResult(
                    success=False,
                    error="interaction_id または task_id + project_id を指定してください"
                )

            # 回答済み検証
            if not skip_validation:
                if interaction.get("status") != "ANSWERED":
                    return ResumeResult(
                        success=False,
                        error=f"Interactionはまだ回答されていません（status={interaction.get('status')}）"
                    )

            # タスク状態確認
            task = fetch_one(
                conn,
                "SELECT * FROM tasks WHERE id = ? AND project_id = ?",
                (task_id, project_id)
            )
            if not task:
                return ResumeResult(
                    success=False,
                    error=f"タスクが見つかりません: {task_id}"
                )

            task_dict = row_to_dict(task)
            current_status = task_dict.get("status")

            # WAITING_INPUT または IN_PROGRESS 状態のみ再開可能
            if current_status not in ("WAITING_INPUT", "IN_PROGRESS"):
                return ResumeResult(
                    success=False,
                    error=f"タスクは再開できません（status={current_status}）"
                )

            # タスク状態をIN_PROGRESSに更新
            if current_status == "WAITING_INPUT":
                execute_query(
                    conn,
                    """
                    UPDATE tasks
                    SET status = 'IN_PROGRESS', updated_at = ?
                    WHERE id = ? AND project_id = ?
                    """,
                    (datetime.now().isoformat(), task_id, project_id)
                )

                # 変更履歴を記録
                record_transition(
                    conn,
                    "task",
                    task_id,
                    "WAITING_INPUT",
                    "IN_PROGRESS",
                    "System",
                    f"ユーザー回答後にタスク再開: {interaction_id}",
                    project_id=project_id,
                )

            # 全Interactionを取得（履歴用）
            all_interactions = get_pending_interactions_for_task(conn, task_id, project_id)
            if interaction and interaction not in all_interactions:
                all_interactions.insert(0, interaction)

            # 再開用コンテキストを構築
            if interaction:
                context = build_resume_context(interaction, all_interactions)
            else:
                context = {
                    "task_id": task_id,
                    "project_id": project_id,
                }

            return ResumeResult(
                success=True,
                task_id=task_id,
                project_id=project_id,
                previous_status=current_status,
                new_status="IN_PROGRESS",
                interaction_id=interaction_id or "",
                question_text=interaction.get("question_text", "") if interaction else "",
                answer_text=interaction.get("answer_text", "") if interaction else "",
                context_for_resume=context,
                message=f"タスクを再開しました: {task_id}"
            )

    except DatabaseError as e:
        return ResumeResult(
            success=False,
            error=f"データベースエラー: {e}"
        )
    except Exception as e:
        return ResumeResult(
            success=False,
            error=f"予期しないエラー: {e}"
        )


def format_resume_prompt(context: Dict[str, Any]) -> str:
    """
    タスク再開用のプロンプトを生成

    Args:
        context: 再開用コンテキスト

    Returns:
        claude -p に渡すプロンプト
    """
    lines = [
        "## タスク再開",
        "",
        f"タスク {context.get('task_id')} の処理を再開します。",
        "",
    ]

    # タスク情報
    task_info = context.get("task_info", {})
    if task_info:
        lines.append("### タスク情報")
        lines.append(f"- タイトル: {task_info.get('title', '不明')}")
        if task_info.get("description"):
            lines.append(f"- 説明: {task_info.get('description')}")
        lines.append("")

    # 最新のやり取り
    latest = context.get("latest_interaction", {})
    if latest:
        lines.append("### ユーザーからの回答")
        lines.append("")
        lines.append(f"**質問**: {latest.get('question', '不明')}")
        lines.append("")
        lines.append(f"**回答**: {latest.get('answer', '不明')}")
        lines.append("")

    # 過去の履歴
    history = context.get("interaction_history", [])
    if len(history) > 1:
        lines.append("### 過去のやり取り")
        for i, h in enumerate(history[1:], 1):
            lines.append(f"{i}. Q: {h.get('question', '')[:50]}... → A: {h.get('answer', '')[:50]}...")
        lines.append("")

    # 指示
    lines.append("### 指示")
    lines.append("")
    lines.append("ユーザーの回答を踏まえて、タスクを継続してください。")

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
        description="タスクを再開",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # Interaction IDで指定
  python resume.py INT_00001

  # タスクID + プロジェクトIDで指定
  python resume.py --task TASK_123 --project AI_PM_PJ

  # プロンプト出力
  python resume.py INT_00001 --json | jq -r '.context_for_resume'
"""
    )

    parser.add_argument(
        "interaction_id",
        nargs="?",
        help="Interaction ID (例: INT_00001)"
    )
    parser.add_argument(
        "--task", "-t",
        help="タスクID"
    )
    parser.add_argument(
        "--project", "-p",
        help="プロジェクトID"
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="回答済み検証をスキップ"
    )
    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="再開用プロンプトを表示"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )

    args = parser.parse_args()

    # 引数チェック
    if not args.interaction_id and not (args.task and args.project):
        print("[ERROR] interaction_id または --task/--project を指定してください", file=sys.stderr)
        sys.exit(1)

    result = resume_task(
        interaction_id=args.interaction_id,
        task_id=args.task,
        project_id=args.project,
        skip_validation=args.skip_validation,
    )

    if args.json:
        output = {
            "success": result.success,
            "task_id": result.task_id,
            "project_id": result.project_id,
            "previous_status": result.previous_status,
            "new_status": result.new_status,
            "interaction_id": result.interaction_id,
            "question_text": result.question_text,
            "answer_text": result.answer_text,
            "context_for_resume": result.context_for_resume,
            "message": result.message,
            "error": result.error,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        if result.success:
            print(f"[OK] {result.message}")
            print(f"  タスク: {result.task_id}")
            print(f"  ステータス: {result.previous_status} → {result.new_status}")
            if result.question_text:
                print(f"  質問: {result.question_text[:50]}...")
            if result.answer_text:
                print(f"  回答: {result.answer_text[:50]}...")

            if args.show_prompt:
                print("\n--- 再開用プロンプト ---")
                print(format_resume_prompt(result.context_for_resume))
        else:
            print(f"[ERROR] {result.error}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
