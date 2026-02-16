#!/usr/bin/env python3
"""
AI PM Framework - Interaction取得スクリプト

単一Interactionの詳細を取得

Usage:
    python backend/interaction/get.py INTERACTION_ID [options]

Options:
    --json              JSON形式で出力

Example:
    python backend/interaction/get.py INT_00001
    python backend/interaction/get.py INT_00001 --json
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import (
    get_connection,
    fetch_one,
    row_to_dict,
    DatabaseError,
)


def get_interaction(
    interaction_id: str,
    *,
    db_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """
    Interactionを取得

    Args:
        interaction_id: Interaction ID
        db_path: データベースパス（テスト用）

    Returns:
        Interactionデータ（存在しない場合はNone）
    """
    try:
        conn = get_connection(db_path=db_path)

        row = fetch_one(
            conn,
            """
            SELECT
                i.*,
                t.title as task_title,
                t.status as task_status,
                o.title as order_title,
                p.name as project_name
            FROM interactions i
            LEFT JOIN tasks t ON i.task_id = t.id AND i.project_id = t.project_id
            LEFT JOIN orders o ON t.order_id = o.id AND t.project_id = o.project_id
            LEFT JOIN projects p ON i.project_id = p.id
            WHERE i.id = ?
            """,
            (interaction_id,)
        )

        conn.close()

        return row_to_dict(row) if row else None

    except DatabaseError as e:
        print(f"[ERROR] データベースエラー: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}", file=sys.stderr)
        return None


def format_interaction_detail(interaction: Dict[str, Any]) -> str:
    """
    Interactionを詳細形式でフォーマット

    Args:
        interaction: Interactionデータ

    Returns:
        詳細形式の文字列
    """
    lines = []
    lines.append(f"# {interaction.get('id', '')}: Interaction詳細")
    lines.append("")
    lines.append("## 基本情報")
    lines.append("")
    lines.append(f"| 項目 | 値 |")
    lines.append(f"|------|-----|")
    lines.append(f"| ID | {interaction.get('id', '')} |")
    lines.append(f"| プロジェクト | {interaction.get('project_name', '')} ({interaction.get('project_id', '')}) |")
    lines.append(f"| タスク | {interaction.get('task_title', '')} ({interaction.get('task_id', '')}) |")
    lines.append(f"| ORDER | {interaction.get('order_title', '')} |")
    lines.append(f"| セッション | {interaction.get('session_id', '')} |")
    lines.append(f"| ステータス | {interaction.get('status', '')} |")
    lines.append(f"| 質問タイプ | {interaction.get('question_type', '')} |")
    lines.append("")
    lines.append("## 質問")
    lines.append("")
    lines.append(interaction.get('question_text', ''))
    lines.append("")

    if interaction.get('options_json'):
        lines.append("## 選択肢")
        lines.append("")
        try:
            options = json.loads(interaction['options_json'])
            for i, opt in enumerate(options, 1):
                lines.append(f"{i}. {opt}")
        except:
            lines.append(interaction['options_json'])
        lines.append("")

    if interaction.get('answer_text'):
        lines.append("## 回答")
        lines.append("")
        lines.append(interaction.get('answer_text', ''))
        lines.append("")

    lines.append("## タイムスタンプ")
    lines.append("")
    lines.append(f"- 作成日時: {interaction.get('created_at', '')}")
    if interaction.get('answered_at'):
        lines.append(f"- 回答日時: {interaction.get('answered_at', '')}")
    if interaction.get('timeout_at'):
        lines.append(f"- タイムアウト: {interaction.get('timeout_at', '')}")
    lines.append(f"- 更新日時: {interaction.get('updated_at', '')}")

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
        description="Interactionを取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python get.py INT_00001
  python get.py INT_00001 --json
"""
    )

    parser.add_argument(
        "interaction_id",
        help="Interaction ID (例: INT_00001)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )

    args = parser.parse_args()

    interaction = get_interaction(args.interaction_id)

    if not interaction:
        print(f"[ERROR] Interactionが見つかりません: {args.interaction_id}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(interaction, ensure_ascii=False, indent=2))
    else:
        print(format_interaction_detail(interaction))


if __name__ == "__main__":
    main()
