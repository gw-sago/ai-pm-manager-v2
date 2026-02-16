#!/usr/bin/env python3
"""
AI PM Framework - Interaction作成スクリプト

AIが質問を発行する際に使用

Usage:
    python backend/interaction/create.py PROJECT_NAME TASK_ID --question "質問内容" [options]

Options:
    --question          質問テキスト（必須）
    --session-id        セッションID（省略時は自動生成）
    --question-type     質問タイプ（GENERAL/CONFIRMATION/CHOICE/INPUT/FILE_SELECT）
    --options           選択肢（JSON配列形式）
    --timeout-minutes   タイムアウト時間（分、デフォルト: 1440 = 24時間）
    --context           コンテキスト情報（JSON形式）
    --json              JSON形式で出力

Example:
    python backend/interaction/create.py AI_PM_PJ TASK_123 --question "どのアプローチを使用しますか？"
    python backend/interaction/create.py AI_PM_PJ TASK_123 --question "続行しますか？" --question-type CONFIRMATION
"""

import argparse
import json
import sys
import uuid
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
    DatabaseError,
)
from utils.validation import (
    validate_project_name,
    validate_task_id,
    project_exists,
    task_exists,
    ValidationError,
)
from utils.transition import (
    validate_transition,
    record_transition,
    TransitionError,
)


# 質問タイプ定義
VALID_QUESTION_TYPES = [
    "GENERAL",        # 一般的な質問
    "CONFIRMATION",   # Yes/No確認
    "CHOICE",         # 選択肢から選択
    "INPUT",          # 自由入力
    "FILE_SELECT",    # ファイル選択
]

# デフォルトタイムアウト（分）
DEFAULT_TIMEOUT_MINUTES = 1440  # 24時間


@dataclass
class CreateInteractionResult:
    """Interaction作成結果"""
    success: bool
    interaction_id: str = ""
    task_id: str = ""
    project_id: str = ""
    question_text: str = ""
    question_type: str = "GENERAL"
    timeout_at: str = ""
    message: str = ""
    error: Optional[str] = None


def get_next_interaction_id(conn) -> str:
    """
    次のInteraction IDを取得

    Args:
        conn: データベース接続

    Returns:
        次のInteraction ID（例: INT_00001）
    """
    row = fetch_one(
        conn,
        """
        SELECT MAX(CAST(SUBSTR(id, 5) AS INTEGER)) as max_num
        FROM interactions
        WHERE id LIKE 'INT_%'
        """
    )

    max_num = row["max_num"] if row and row["max_num"] else 0
    next_num = max_num + 1

    return f"INT_{next_num:05d}"


def create_interaction(
    project_id: str,
    task_id: str,
    question_text: str,
    *,
    session_id: Optional[str] = None,
    question_type: str = "GENERAL",
    options: Optional[List[str]] = None,
    timeout_minutes: int = DEFAULT_TIMEOUT_MINUTES,
    context: Optional[Dict[str, Any]] = None,
    db_path: Optional[Path] = None,
) -> CreateInteractionResult:
    """
    Interactionを作成

    AIが質問を発行し、ユーザーの回答を待つ状態を作成

    Args:
        project_id: プロジェクトID
        task_id: タスクID
        question_text: 質問テキスト
        session_id: セッションID（省略時は自動生成）
        question_type: 質問タイプ
        options: 選択肢（CHOICE時に使用）
        timeout_minutes: タイムアウト時間（分）
        context: コンテキスト情報
        db_path: データベースパス（テスト用）

    Returns:
        CreateInteractionResult: 作成結果
    """
    try:
        # 入力検証
        validate_project_name(project_id)
        validate_task_id(task_id)

        if not question_text or not question_text.strip():
            return CreateInteractionResult(
                success=False,
                error="質問テキストは必須です"
            )

        if question_type not in VALID_QUESTION_TYPES:
            return CreateInteractionResult(
                success=False,
                error=f"無効な質問タイプ: {question_type}\n有効なタイプ: {', '.join(VALID_QUESTION_TYPES)}"
            )

        with transaction(db_path=db_path) as conn:
            # プロジェクト存在確認
            if not project_exists(conn, project_id):
                return CreateInteractionResult(
                    success=False,
                    error=f"プロジェクトが見つかりません: {project_id}"
                )

            # タスク存在確認
            if not task_exists(conn, task_id, project_id):
                return CreateInteractionResult(
                    success=False,
                    error=f"タスクが見つかりません: {task_id}"
                )

            # Interaction ID生成
            interaction_id = get_next_interaction_id(conn)

            # セッションID生成（未指定の場合）
            if not session_id:
                session_id = f"SESSION_{uuid.uuid4().hex[:8].upper()}"

            # タイムアウト時刻計算
            now = datetime.now()
            timeout_at = now + timedelta(minutes=timeout_minutes)

            # オプション・コンテキストをJSON化
            options_json = json.dumps(options, ensure_ascii=False) if options else None
            context_json = json.dumps(context, ensure_ascii=False) if context else None

            # DB INSERT
            execute_query(
                conn,
                """
                INSERT INTO interactions (
                    id, session_id, task_id, project_id,
                    question_text, status, question_type,
                    options_json, context_snapshot, timeout_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?, ?, ?, ?, ?)
                """,
                (
                    interaction_id, session_id, task_id, project_id,
                    question_text.strip(), question_type,
                    options_json, context_json, timeout_at.isoformat(),
                    now.isoformat(), now.isoformat()
                )
            )

            # 変更履歴を記録
            record_transition(
                conn,
                "interaction",
                interaction_id,
                None,
                "PENDING",
                "System",
                f"質問作成: {question_text[:50]}..."
            )

            return CreateInteractionResult(
                success=True,
                interaction_id=interaction_id,
                task_id=task_id,
                project_id=project_id,
                question_text=question_text,
                question_type=question_type,
                timeout_at=timeout_at.isoformat(),
                message=f"Interactionを作成しました: {interaction_id}"
            )

    except ValidationError as e:
        return CreateInteractionResult(
            success=False,
            error=f"入力検証エラー: {e}"
        )
    except TransitionError as e:
        return CreateInteractionResult(
            success=False,
            error=f"状態遷移エラー: {e}"
        )
    except DatabaseError as e:
        return CreateInteractionResult(
            success=False,
            error=f"データベースエラー: {e}"
        )
    except Exception as e:
        return CreateInteractionResult(
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
        description="Interactionを作成（AI質問発行）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 基本的な質問
  python create.py AI_PM_PJ TASK_123 --question "どのアプローチを使用しますか？"

  # 確認質問
  python create.py AI_PM_PJ TASK_123 --question "続行しますか？" --question-type CONFIRMATION

  # 選択肢付き
  python create.py AI_PM_PJ TASK_123 --question "言語は？" --question-type CHOICE --options '["Python","JavaScript","TypeScript"]'

質問タイプ:
  GENERAL      - 一般的な質問
  CONFIRMATION - Yes/No確認
  CHOICE       - 選択肢から選択
  INPUT        - 自由入力
  FILE_SELECT  - ファイル選択
"""
    )

    parser.add_argument(
        "project_id",
        help="プロジェクトID (例: AI_PM_PJ)"
    )
    parser.add_argument(
        "task_id",
        help="タスクID (例: TASK_123)"
    )
    parser.add_argument(
        "--question", "-q",
        required=True,
        help="質問テキスト"
    )
    parser.add_argument(
        "--session-id",
        help="セッションID（省略時は自動生成）"
    )
    parser.add_argument(
        "--question-type", "-t",
        choices=VALID_QUESTION_TYPES,
        default="GENERAL",
        help="質問タイプ（デフォルト: GENERAL）"
    )
    parser.add_argument(
        "--options",
        help="選択肢（JSON配列形式）"
    )
    parser.add_argument(
        "--timeout-minutes",
        type=int,
        default=DEFAULT_TIMEOUT_MINUTES,
        help=f"タイムアウト時間（分、デフォルト: {DEFAULT_TIMEOUT_MINUTES}）"
    )
    parser.add_argument(
        "--context",
        help="コンテキスト情報（JSON形式）"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )

    args = parser.parse_args()

    # オプションのパース
    options = None
    if args.options:
        try:
            options = json.loads(args.options)
        except json.JSONDecodeError as e:
            print(f"[ERROR] 無効なJSON形式（options）: {e}", file=sys.stderr)
            sys.exit(1)

    context = None
    if args.context:
        try:
            context = json.loads(args.context)
        except json.JSONDecodeError as e:
            print(f"[ERROR] 無効なJSON形式（context）: {e}", file=sys.stderr)
            sys.exit(1)

    result = create_interaction(
        project_id=args.project_id,
        task_id=args.task_id,
        question_text=args.question,
        session_id=args.session_id,
        question_type=args.question_type,
        options=options,
        timeout_minutes=args.timeout_minutes,
        context=context,
    )

    if args.json:
        output = {
            "success": result.success,
            "interaction_id": result.interaction_id,
            "task_id": result.task_id,
            "project_id": result.project_id,
            "question_text": result.question_text,
            "question_type": result.question_type,
            "timeout_at": result.timeout_at,
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
            print(f"  タイプ: {result.question_type}")
            print(f"  タイムアウト: {result.timeout_at}")
        else:
            print(f"[ERROR] {result.error}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
