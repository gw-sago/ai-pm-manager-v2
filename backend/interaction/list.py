#!/usr/bin/env python3
"""
AI PM Framework - Interaction一覧スクリプト

Interaction一覧を取得

Usage:
    python backend/interaction/list.py [PROJECT_ID] [options]

Options:
    --status            ステータスでフィルタ（PENDING/ANSWERED/TIMEOUT/CANCELLED/SKIPPED）
    --task-id           タスクIDでフィルタ
    --pending           PENDINGのみ表示（--status PENDINGと同等）
    --limit             取得件数制限（デフォルト: 50）
    --json              JSON形式で出力

Example:
    python backend/interaction/list.py AI_PM_PJ
    python backend/interaction/list.py AI_PM_PJ --pending
    python backend/interaction/list.py --status PENDING --json
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import (
    get_connection,
    fetch_all,
    row_to_dict,
    DatabaseError,
)


# ステータス定義
VALID_STATUSES = ["PENDING", "ANSWERED", "TIMEOUT", "CANCELLED", "SKIPPED"]


def list_interactions(
    project_id: Optional[str] = None,
    *,
    status: Optional[str] = None,
    task_id: Optional[str] = None,
    limit: int = 50,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """
    Interaction一覧を取得

    Args:
        project_id: プロジェクトID（省略時は全プロジェクト）
        status: ステータスフィルタ
        task_id: タスクIDフィルタ
        limit: 取得件数制限
        db_path: データベースパス（テスト用）

    Returns:
        Interaction一覧
    """
    try:
        conn = get_connection(db_path=db_path)

        # クエリ構築
        query = """
            SELECT
                i.*,
                t.title as task_title,
                t.status as task_status
            FROM interactions i
            LEFT JOIN tasks t ON i.task_id = t.id AND i.project_id = t.project_id
            WHERE 1=1
        """
        params = []

        if project_id:
            query += " AND i.project_id = ?"
            params.append(project_id)

        if status:
            query += " AND i.status = ?"
            params.append(status)

        if task_id:
            query += " AND i.task_id = ?"
            params.append(task_id)

        query += " ORDER BY i.created_at DESC LIMIT ?"
        params.append(limit)

        rows = fetch_all(conn, query, tuple(params))
        conn.close()

        return [row_to_dict(row) for row in rows]

    except DatabaseError as e:
        print(f"[ERROR] データベースエラー: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}", file=sys.stderr)
        return []


def format_interaction_table(interactions: List[Dict[str, Any]]) -> str:
    """
    Interactionをテーブル形式でフォーマット

    Args:
        interactions: Interaction一覧

    Returns:
        テーブル形式の文字列
    """
    if not interactions:
        return "Interactionが見つかりません"

    lines = []
    lines.append("| ID | プロジェクト | タスク | ステータス | 質問 | 作成日時 |")
    lines.append("|----|-----------|----|----------|-----|-------|")

    for i in interactions:
        question_preview = i.get("question_text", "")[:30]
        if len(i.get("question_text", "")) > 30:
            question_preview += "..."

        created = i.get("created_at", "")
        if created:
            try:
                dt = datetime.fromisoformat(created)
                created = dt.strftime("%m/%d %H:%M")
            except:
                created = created[:16]

        lines.append(
            f"| {i.get('id', '')} "
            f"| {i.get('project_id', '')} "
            f"| {i.get('task_id', '')} "
            f"| {i.get('status', '')} "
            f"| {question_preview} "
            f"| {created} |"
        )

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
        description="Interaction一覧を取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # プロジェクト指定
  python list.py AI_PM_PJ

  # 待機中のみ
  python list.py AI_PM_PJ --pending

  # ステータス指定
  python list.py --status ANSWERED

  # JSON出力
  python list.py AI_PM_PJ --json

ステータス:
  PENDING   - 回答待ち
  ANSWERED  - 回答済み
  TIMEOUT   - タイムアウト
  CANCELLED - キャンセル
  SKIPPED   - スキップ
"""
    )

    parser.add_argument(
        "project_id",
        nargs="?",
        help="プロジェクトID (例: AI_PM_PJ)"
    )
    parser.add_argument(
        "--status", "-s",
        choices=VALID_STATUSES,
        help="ステータスでフィルタ"
    )
    parser.add_argument(
        "--task-id", "-t",
        help="タスクIDでフィルタ"
    )
    parser.add_argument(
        "--pending",
        action="store_true",
        help="PENDINGのみ表示"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=50,
        help="取得件数制限（デフォルト: 50）"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )

    args = parser.parse_args()

    # --pending は --status PENDING と同等
    status = args.status
    if args.pending:
        status = "PENDING"

    interactions = list_interactions(
        project_id=args.project_id,
        status=status,
        task_id=args.task_id,
        limit=args.limit,
    )

    if args.json:
        print(json.dumps(interactions, ensure_ascii=False, indent=2))
    else:
        print(format_interaction_table(interactions))
        print(f"\n合計: {len(interactions)}件")


if __name__ == "__main__":
    main()
