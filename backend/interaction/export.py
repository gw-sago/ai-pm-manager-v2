#!/usr/bin/env python3
"""
AI PM Framework - 対話ログMD出力

interactionsデータをMarkdownファイルに出力

Usage:
    # タスク単位で出力
    python backend/interaction/export.py --task TASK_ID --project PROJECT_ID

    # ORDER単位で出力
    python backend/interaction/export.py --order ORDER_ID --project PROJECT_ID

    # プロジェクト全体
    python backend/interaction/export.py --project PROJECT_ID

Options:
    --task              タスクIDでフィルタ
    --order             ORDER IDでフィルタ
    --project           プロジェクトID（必須）
    --output            出力先パス（省略時は標準出力）
    --format            出力形式（markdown/json、デフォルト: markdown）
    --include-pending   PENDINGも含める
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
    rows_to_dicts,
    DatabaseError,
)


def get_interactions(
    conn,
    project_id: str,
    *,
    task_id: Optional[str] = None,
    order_id: Optional[str] = None,
    include_pending: bool = False,
) -> List[Dict[str, Any]]:
    """
    Interaction一覧を取得

    Args:
        conn: データベース接続
        project_id: プロジェクトID
        task_id: タスクID（フィルタ）
        order_id: ORDER ID（フィルタ）
        include_pending: PENDINGも含める

    Returns:
        Interaction一覧
    """
    query = """
        SELECT
            i.*,
            t.title as task_title,
            t.order_id,
            o.title as order_title
        FROM interactions i
        LEFT JOIN tasks t ON i.task_id = t.id AND i.project_id = t.project_id
        LEFT JOIN orders o ON t.order_id = o.id AND t.project_id = o.project_id
        WHERE i.project_id = ?
    """
    params = [project_id]

    if task_id:
        query += " AND i.task_id = ?"
        params.append(task_id)

    if order_id:
        query += " AND t.order_id = ?"
        params.append(order_id)

    if not include_pending:
        query += " AND i.status != 'PENDING'"

    query += " ORDER BY i.created_at ASC"

    rows = fetch_all(conn, query, tuple(params))
    return rows_to_dicts(rows)


def format_datetime(dt_str: Optional[str]) -> str:
    """日時をフォーマット"""
    if not dt_str:
        return "-"
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return dt_str


def calculate_response_time(interaction: Dict[str, Any]) -> str:
    """応答時間を計算"""
    created = interaction.get("created_at")
    answered = interaction.get("answered_at")

    if not created or not answered:
        return "-"

    try:
        created_dt = datetime.fromisoformat(created)
        answered_dt = datetime.fromisoformat(answered)
        delta = answered_dt - created_dt
        minutes = int(delta.total_seconds() / 60)

        if minutes < 60:
            return f"{minutes}分"
        elif minutes < 1440:
            hours = minutes // 60
            mins = minutes % 60
            return f"{hours}時間{mins}分"
        else:
            days = minutes // 1440
            hours = (minutes % 1440) // 60
            return f"{days}日{hours}時間"
    except (ValueError, TypeError):
        return "-"


def format_as_markdown(
    interactions: List[Dict[str, Any]],
    *,
    project_id: str,
    task_id: Optional[str] = None,
    order_id: Optional[str] = None,
) -> str:
    """
    InteractionをMarkdown形式でフォーマット

    Args:
        interactions: Interaction一覧
        project_id: プロジェクトID
        task_id: タスクID
        order_id: ORDER ID

    Returns:
        Markdown形式の文字列
    """
    lines = []

    # タイトル
    if task_id:
        lines.append(f"# 対話ログ: {task_id}")
    elif order_id:
        lines.append(f"# 対話ログ: {order_id}")
    else:
        lines.append(f"# 対話ログ: {project_id}")

    lines.append("")
    lines.append(f"**出力日時**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**件数**: {len(interactions)}件")
    lines.append("")

    if not interactions:
        lines.append("対話ログはありません。")
        return "\n".join(lines)

    # サマリテーブル
    lines.append("## サマリ")
    lines.append("")
    lines.append("| ID | タスク | ステータス | 作成日時 | 応答時間 |")
    lines.append("|----|----|----------|-------|------|")

    for i in interactions:
        response_time = calculate_response_time(i)
        lines.append(
            f"| {i.get('id', '')} "
            f"| {i.get('task_id', '')} "
            f"| {i.get('status', '')} "
            f"| {format_datetime(i.get('created_at'))[:16]} "
            f"| {response_time} |"
        )

    lines.append("")

    # 詳細
    lines.append("## 詳細")
    lines.append("")

    current_order = None
    current_task = None

    for i in interactions:
        # ORDER区切り
        order = i.get("order_id")
        if order != current_order:
            current_order = order
            order_title = i.get("order_title", "")
            lines.append(f"### ORDER: {order}")
            if order_title:
                lines.append(f"*{order_title}*")
            lines.append("")
            current_task = None

        # TASK区切り
        task = i.get("task_id")
        if task != current_task:
            current_task = task
            task_title = i.get("task_title", "")
            lines.append(f"#### TASK: {task}")
            if task_title:
                lines.append(f"*{task_title}*")
            lines.append("")

        # Interaction詳細
        lines.append(f"**[{i.get('id')}]** {i.get('status')} - {format_datetime(i.get('created_at'))}")
        lines.append("")

        # 質問
        lines.append(f"**Q**: {i.get('question_text', '')}")
        lines.append("")

        # 選択肢
        if i.get("options_json"):
            try:
                options = json.loads(i["options_json"])
                if options:
                    lines.append("*選択肢*:")
                    for idx, opt in enumerate(options, 1):
                        lines.append(f"  {idx}. {opt}")
                    lines.append("")
            except json.JSONDecodeError:
                pass

        # 回答
        answer = i.get("answer_text", "")
        if answer:
            lines.append(f"**A**: {answer}")
            lines.append("")
            lines.append(f"*回答日時*: {format_datetime(i.get('answered_at'))} (*応答時間*: {calculate_response_time(i)})")
        else:
            status = i.get("status")
            if status == "PENDING":
                lines.append("**A**: (回答待ち)")
            elif status == "TIMEOUT":
                lines.append("**A**: (タイムアウト)")
            elif status == "CANCELLED":
                lines.append("**A**: (キャンセル)")
            elif status == "SKIPPED":
                lines.append("**A**: (スキップ)")

        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def export_interactions(
    project_id: str,
    *,
    task_id: Optional[str] = None,
    order_id: Optional[str] = None,
    output_path: Optional[str] = None,
    output_format: str = "markdown",
    include_pending: bool = False,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Interactionをエクスポート

    Args:
        project_id: プロジェクトID
        task_id: タスクID（フィルタ）
        order_id: ORDER ID（フィルタ）
        output_path: 出力先パス
        output_format: 出力形式（markdown/json）
        include_pending: PENDINGも含める
        db_path: データベースパス（テスト用）

    Returns:
        処理結果
    """
    try:
        conn = get_connection(db_path=db_path)

        # データ取得
        interactions = get_interactions(
            conn,
            project_id,
            task_id=task_id,
            order_id=order_id,
            include_pending=include_pending,
        )

        conn.close()

        # フォーマット
        if output_format == "json":
            content = json.dumps(interactions, ensure_ascii=False, indent=2)
        else:
            content = format_as_markdown(
                interactions,
                project_id=project_id,
                task_id=task_id,
                order_id=order_id,
            )

        # 出力
        if output_path:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(content, encoding="utf-8")
            return {
                "success": True,
                "count": len(interactions),
                "output_path": str(output_file),
                "message": f"{len(interactions)}件をエクスポートしました: {output_file}"
            }
        else:
            return {
                "success": True,
                "count": len(interactions),
                "content": content,
                "message": f"{len(interactions)}件をエクスポートしました"
            }

    except DatabaseError as e:
        return {"success": False, "error": f"データベースエラー: {e}"}
    except Exception as e:
        return {"success": False, "error": f"予期しないエラー: {e}"}


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
        description="対話ログをMarkdown/JSONで出力",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # タスク単位
  python export.py --task TASK_123 --project AI_PM_PJ

  # ORDER単位
  python export.py --order ORDER_102 --project AI_PM_PJ

  # ファイルに出力
  python export.py --project AI_PM_PJ --output logs/interactions.md

  # JSON形式
  python export.py --project AI_PM_PJ --format json
"""
    )

    parser.add_argument(
        "--task", "-t",
        help="タスクIDでフィルタ"
    )
    parser.add_argument(
        "--order", "-o",
        help="ORDER IDでフィルタ"
    )
    parser.add_argument(
        "--project", "-p",
        required=True,
        help="プロジェクトID（必須）"
    )
    parser.add_argument(
        "--output",
        help="出力先パス（省略時は標準出力）"
    )
    parser.add_argument(
        "--format", "-f",
        choices=["markdown", "json"],
        default="markdown",
        help="出力形式（デフォルト: markdown）"
    )
    parser.add_argument(
        "--include-pending",
        action="store_true",
        help="PENDINGも含める"
    )

    args = parser.parse_args()

    result = export_interactions(
        project_id=args.project,
        task_id=args.task,
        order_id=args.order,
        output_path=args.output,
        output_format=args.format,
        include_pending=args.include_pending,
    )

    if result.get("success"):
        if args.output:
            print(f"[OK] {result.get('message')}")
        else:
            print(result.get("content", ""))
    else:
        print(f"[ERROR] {result.get('error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
