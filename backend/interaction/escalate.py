#!/usr/bin/env python3
"""
AI PM Framework - Interactionエスカレーションスクリプト

ユーザーがAIの質問をキャンセル/エスカレーションする際に使用

Usage:
    python backend/interaction/escalate.py INTERACTION_ID [--reason "理由"]

Options:
    --reason            エスカレーション理由
    --json              JSON形式で出力

Example:
    python backend/interaction/escalate.py INT_00001 --reason "判断不能"
    python backend/interaction/escalate.py INT_00001 --json
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
    row_to_dict,
    DatabaseError,
)
from utils.transition import (
    record_transition,
    TransitionError,
)


@dataclass
class EscalateInteractionResult:
    """Interactionエスカレーション結果"""
    success: bool
    interaction_id: str = ""
    task_id: str = ""
    project_id: str = ""
    question_text: str = ""
    reason: str = ""
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


def escalate_interaction(
    interaction_id: str,
    reason: str = "ユーザーによるキャンセル",
    *,
    db_path: Optional[Path] = None,
) -> EscalateInteractionResult:
    """
    Interactionをエスカレーション

    ユーザーがキャンセルした場合、ステータスをESCALATED（またはCANCELLED）に更新

    Args:
        interaction_id: Interaction ID
        reason: エスカレーション理由
        db_path: データベースパス（テスト用）

    Returns:
        EscalateInteractionResult: エスカレーション結果
    """
    try:
        if not interaction_id or not interaction_id.strip():
            return EscalateInteractionResult(
                success=False,
                error="Interaction IDは必須です"
            )

        with transaction(db_path=db_path) as conn:
            # Interaction存在確認
            interaction = get_interaction(conn, interaction_id)
            if not interaction:
                return EscalateInteractionResult(
                    success=False,
                    error=f"Interactionが見つかりません: {interaction_id}"
                )

            previous_status = interaction["status"]

            # ステータスチェック
            if previous_status not in ("PENDING", "WAITING"):
                return EscalateInteractionResult(
                    success=False,
                    error=f"このInteractionはエスカレーションできません（現在のステータス: {previous_status}）"
                )

            # DB UPDATE - CANCELLEDステータスに更新
            # ESCALATEDがない場合はCANCELLEDを使用
            new_status = "CANCELLED"  # または ESCALATED
            now = datetime.now()

            execute_query(
                conn,
                """
                UPDATE interactions
                SET status = ?,
                    answer_text = ?,
                    answered_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    new_status,
                    f"[ESCALATED] {reason}",
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
                previous_status,
                new_status,
                "User",
                f"エスカレーション: {reason[:100]}"
            )

            return EscalateInteractionResult(
                success=True,
                interaction_id=interaction_id,
                task_id=interaction["task_id"],
                project_id=interaction["project_id"],
                question_text=interaction["question_text"],
                reason=reason,
                previous_status=previous_status,
                new_status=new_status,
                message=f"エスカレーションしました: {interaction_id}"
            )

    except DatabaseError as e:
        return EscalateInteractionResult(
            success=False,
            error=f"データベースエラー: {e}"
        )
    except Exception as e:
        return EscalateInteractionResult(
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
        description="Interactionをエスカレーション（キャンセル）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python escalate.py INT_00001
  python escalate.py INT_00001 --reason "判断不能"
  python escalate.py INT_00001 --json
"""
    )

    parser.add_argument(
        "interaction_id",
        help="Interaction ID (例: INT_00001)"
    )
    parser.add_argument(
        "--reason", "-r",
        default="ユーザーによるキャンセル",
        help="エスカレーション理由"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )

    args = parser.parse_args()

    result = escalate_interaction(
        interaction_id=args.interaction_id,
        reason=args.reason,
    )

    if args.json:
        output = {
            "success": result.success,
            "interaction_id": result.interaction_id,
            "task_id": result.task_id,
            "project_id": result.project_id,
            "question_text": result.question_text,
            "reason": result.reason,
            "previous_status": result.previous_status,
            "new_status": result.new_status,
            "message": result.message,
            "error": result.error,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        if result.success:
            print(f"[OK] {result.message}")
            print(f"  ID: {result.interaction_id}")
            print(f"  タスク: {result.task_id}")
            print(f"  質問: {result.question_text[:50]}...")
            print(f"  理由: {result.reason}")
            print(f"  ステータス: {result.previous_status} → {result.new_status}")
        else:
            print(f"[ERROR] {result.error}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
