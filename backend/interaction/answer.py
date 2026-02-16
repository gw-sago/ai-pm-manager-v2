#!/usr/bin/env python3
"""
AI PM Framework - Interaction回答スクリプト

ユーザーがAIの質問に回答する際に使用

Usage:
    python backend/interaction/answer.py INTERACTION_ID --answer "回答内容"

Options:
    --answer            回答テキスト（必須）
    --auto-resume       回答保存後にタスクを自動再開（WAITING_INPUT → IN_PROGRESS）
    --json              JSON形式で出力

Example:
    python backend/interaction/answer.py INT_00001 --answer "オプションAを使用"
    python backend/interaction/answer.py INT_00001 --answer "はい" --auto-resume
"""

import argparse
import json
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
    fetch_all,
    row_to_dict,
    DatabaseError,
)
from utils.transition import (
    validate_transition,
    record_transition,
    TransitionError,
)


@dataclass
class AnswerInteractionResult:
    """Interaction回答結果"""
    success: bool
    interaction_id: str = ""
    task_id: str = ""
    project_id: str = ""
    question_text: str = ""
    answer_text: str = ""
    previous_status: str = ""
    new_status: str = ""
    message: str = ""
    error: Optional[str] = None


def get_interaction(conn, interaction_id: str) -> Optional[dict]:
    """
    Interactionを取得

    Args:
        conn: データベース接続
        interaction_id: Interaction ID

    Returns:
        Interactionデータ（存在しない場合はNone）
    """
    row = fetch_one(
        conn,
        """
        SELECT * FROM interactions WHERE id = ?
        """,
        (interaction_id,)
    )
    return row_to_dict(row) if row else None


def answer_interaction(
    interaction_id: str,
    answer_text: str,
    *,
    db_path: Optional[Path] = None,
) -> AnswerInteractionResult:
    """
    Interactionに回答

    ユーザーの回答を保存し、ステータスをANSWEREDに更新

    Args:
        interaction_id: Interaction ID
        answer_text: 回答テキスト
        db_path: データベースパス（テスト用）

    Returns:
        AnswerInteractionResult: 回答結果
    """
    try:
        if not interaction_id or not interaction_id.strip():
            return AnswerInteractionResult(
                success=False,
                error="Interaction IDは必須です"
            )

        if not answer_text or not answer_text.strip():
            return AnswerInteractionResult(
                success=False,
                error="回答テキストは必須です"
            )

        with transaction(db_path=db_path) as conn:
            # Interaction存在確認
            interaction = get_interaction(conn, interaction_id)
            if not interaction:
                return AnswerInteractionResult(
                    success=False,
                    error=f"Interactionが見つかりません: {interaction_id}"
                )

            previous_status = interaction["status"]

            # ステータスチェック
            if previous_status != "PENDING":
                return AnswerInteractionResult(
                    success=False,
                    error=f"このInteractionは回答できません（現在のステータス: {previous_status}）"
                )

            # 状態遷移検証
            try:
                validate_transition(conn, "interaction", "PENDING", "ANSWERED", "ANY")
            except TransitionError:
                # interaction用の遷移がない場合は許可
                pass

            # DB UPDATE
            now = datetime.now()
            execute_query(
                conn,
                """
                UPDATE interactions
                SET answer_text = ?,
                    status = 'ANSWERED',
                    answered_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    answer_text.strip(),
                    now.isoformat(),
                    now.isoformat(),
                    interaction_id
                )
            )

            # 変更履歴を記録
            record_transition(
                conn,
                "interaction",
                interaction_id,
                "PENDING",
                "ANSWERED",
                "User",
                f"回答: {answer_text[:50]}..."
            )

            return AnswerInteractionResult(
                success=True,
                interaction_id=interaction_id,
                task_id=interaction["task_id"],
                project_id=interaction["project_id"],
                question_text=interaction["question_text"],
                answer_text=answer_text,
                previous_status=previous_status,
                new_status="ANSWERED",
                message=f"回答を保存しました: {interaction_id}"
            )

    except DatabaseError as e:
        return AnswerInteractionResult(
            success=False,
            error=f"データベースエラー: {e}"
        )
    except Exception as e:
        return AnswerInteractionResult(
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
        description="Interactionに回答",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python answer.py INT_00001 --answer "オプションAを使用"
  python answer.py INT_00001 --answer "はい" --auto-resume
  python answer.py INT_00001 --answer "はい" --json
"""
    )

    parser.add_argument(
        "interaction_id",
        help="Interaction ID (例: INT_00001)"
    )
    parser.add_argument(
        "--answer", "-a",
        required=True,
        help="回答テキスト"
    )
    parser.add_argument(
        "--auto-resume",
        action="store_true",
        help="回答保存後にタスクを自動再開"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )

    args = parser.parse_args()

    result = answer_interaction(
        interaction_id=args.interaction_id,
        answer_text=args.answer,
    )

    # 自動再開オプション
    resume_result = None
    if result.success and args.auto_resume:
        try:
            from interaction.resume import resume_task
            resume_result = resume_task(
                interaction_id=args.interaction_id,
            )
        except Exception as e:
            resume_result = {"success": False, "error": str(e)}

    if args.json:
        output = {
            "success": result.success,
            "interaction_id": result.interaction_id,
            "task_id": result.task_id,
            "project_id": result.project_id,
            "question_text": result.question_text,
            "answer_text": result.answer_text,
            "previous_status": result.previous_status,
            "new_status": result.new_status,
            "message": result.message,
            "error": result.error,
        }
        if resume_result:
            output["resume_result"] = {
                "success": resume_result.success if hasattr(resume_result, 'success') else resume_result.get("success"),
                "task_status": resume_result.new_status if hasattr(resume_result, 'new_status') else resume_result.get("new_status"),
                "error": resume_result.error if hasattr(resume_result, 'error') else resume_result.get("error"),
            }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        if result.success:
            print(f"[OK] {result.message}")
            print(f"  ID: {result.interaction_id}")
            print(f"  タスク: {result.task_id}")
            print(f"  質問: {result.question_text[:50]}...")
            print(f"  回答: {result.answer_text[:50]}...")
            print(f"  ステータス: {result.previous_status} → {result.new_status}")
            if resume_result:
                if hasattr(resume_result, 'success') and resume_result.success:
                    print(f"  【自動再開】タスク状態: {resume_result.previous_status} → {resume_result.new_status}")
                elif isinstance(resume_result, dict) and resume_result.get("success"):
                    print(f"  【自動再開】成功")
                else:
                    error = resume_result.error if hasattr(resume_result, 'error') else resume_result.get("error", "不明")
                    print(f"  【自動再開】失敗: {error}")
        else:
            print(f"[ERROR] {result.error}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
