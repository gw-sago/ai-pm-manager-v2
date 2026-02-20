#!/usr/bin/env python3
"""
AI PM Framework - プロジェクト紹介ページ生成スクリプト

プロジェクトの情報（ステータス・ORDER進捗・タスク統計等）をもとに
HTML形式の紹介ページを生成する。

Usage:
    python backend/project/generate_page.py PROJECT_ID [--json]

Arguments:
    PROJECT_ID    プロジェクトID（例: ai_pm_manager_v2）

Options:
    --json        JSON形式で出力

Output:
    成功時:
        {"success": true, "html": "<html>...</html>"}
    エラー時:
        {"success": false, "error": "..."}

Example:
    python backend/project/generate_page.py ai_pm_manager_v2 --json
"""

import argparse
import html
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import (
    get_connection,
    fetch_one,
    fetch_all,
    rows_to_dicts,
    DatabaseError,
)
from utils.validation import (
    validate_project_name,
    project_exists,
    ValidationError,
)


def _get_project_info(conn, project_id: str) -> Optional[Dict[str, Any]]:
    """
    プロジェクト基本情報を取得

    Args:
        conn: データベース接続
        project_id: プロジェクトID

    Returns:
        プロジェクト情報の辞書、見つからない場合はNone
    """
    row = fetch_one(
        conn,
        """
        SELECT id, name, path, status, current_order_id, created_at, updated_at
        FROM projects WHERE id = ?
        """,
        (project_id,)
    )
    if row is None:
        return None
    return dict(row)


def _get_order_summary(conn, project_id: str) -> List[Dict[str, Any]]:
    """
    ORDER一覧のサマリを取得

    Args:
        conn: データベース接続
        project_id: プロジェクトID

    Returns:
        ORDER情報のリスト
    """
    rows = fetch_all(
        conn,
        """
        SELECT id, title, status, created_at, updated_at
        FROM orders
        WHERE project_id = ?
        ORDER BY
            CASE status
                WHEN 'IN_PROGRESS' THEN 0
                WHEN 'REVIEW' THEN 1
                WHEN 'PLANNING' THEN 2
                WHEN 'COMPLETED' THEN 3
                ELSE 4
            END,
            created_at DESC
        LIMIT 20
        """,
        (project_id,)
    )
    return rows_to_dicts(rows)


def _get_task_stats(conn, project_id: str) -> Dict[str, int]:
    """
    タスク統計を取得

    Args:
        conn: データベース接続
        project_id: プロジェクトID

    Returns:
        タスク統計の辞書
    """
    row = fetch_one(
        conn,
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN status = 'IN_PROGRESS' THEN 1 ELSE 0 END) as in_progress,
            SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN status = 'REJECTED' THEN 1 ELSE 0 END) as rejected
        FROM tasks WHERE project_id = ?
        """,
        (project_id,)
    )
    if row:
        return {
            "total": row["total"] or 0,
            "completed": row["completed"] or 0,
            "in_progress": row["in_progress"] or 0,
            "pending": row["pending"] or 0,
            "rejected": row["rejected"] or 0,
        }
    return {"total": 0, "completed": 0, "in_progress": 0, "pending": 0, "rejected": 0}


def _get_backlog_stats(conn, project_id: str) -> Dict[str, int]:
    """
    バックログ統計を取得

    Args:
        conn: データベース接続
        project_id: プロジェクトID

    Returns:
        バックログ統計の辞書
    """
    row = fetch_one(
        conn,
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'TODO' THEN 1 ELSE 0 END) as todo,
            SUM(CASE WHEN status = 'IN_PROGRESS' THEN 1 ELSE 0 END) as in_progress,
            SUM(CASE WHEN status = 'DONE' THEN 1 ELSE 0 END) as done
        FROM backlog_items WHERE project_id = ?
        """,
        (project_id,)
    )
    if row:
        return {
            "total": row["total"] or 0,
            "todo": row["todo"] or 0,
            "in_progress": row["in_progress"] or 0,
            "done": row["done"] or 0,
        }
    return {"total": 0, "todo": 0, "in_progress": 0, "done": 0}


def _escape(text: Any) -> str:
    """HTML エスケープ"""
    return html.escape(str(text)) if text else ""


def _status_badge(status: str) -> str:
    """ステータスに応じたバッジHTMLを返す"""
    color_map = {
        "IN_PROGRESS": "#2196F3",
        "COMPLETED": "#4CAF50",
        "REVIEW": "#FF9800",
        "PLANNING": "#9C27B0",
        "REWORK": "#F44336",
        "PENDING": "#607D8B",
        "TODO": "#607D8B",
        "DONE": "#4CAF50",
        "CANCELLED": "#9E9E9E",
        "ON_HOLD": "#795548",
        "REJECTED": "#F44336",
    }
    color = color_map.get(status, "#607D8B")
    return f'<span style="display:inline-block;padding:2px 8px;border-radius:4px;background:{color};color:#fff;font-size:12px;">{_escape(status)}</span>'


def _build_html(
    project: Dict[str, Any],
    orders: List[Dict[str, Any]],
    task_stats: Dict[str, int],
    backlog_stats: Dict[str, int],
) -> str:
    """
    HTMLページを構築

    Args:
        project: プロジェクト基本情報
        orders: ORDER一覧
        task_stats: タスク統計
        backlog_stats: バックログ統計

    Returns:
        HTML文字列
    """
    project_name = _escape(project.get("name") or project.get("id", ""))
    project_id = _escape(project.get("id", ""))
    project_status = project.get("status", "UNKNOWN")
    created_at = _escape(project.get("created_at", ""))
    updated_at = _escape(project.get("updated_at", ""))

    # タスク進捗率
    task_total = task_stats["total"]
    task_completed = task_stats["completed"]
    progress_pct = round((task_completed / task_total) * 100) if task_total > 0 else 0

    # ORDER一覧のHTML
    order_rows = ""
    for o in orders:
        order_rows += f"""
        <tr>
            <td>{_escape(o.get('id', ''))}</td>
            <td>{_escape(o.get('title', ''))}</td>
            <td>{_status_badge(o.get('status', ''))}</td>
            <td>{_escape(o.get('created_at', ''))}</td>
        </tr>"""

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{project_name} - プロジェクト紹介</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', 'Meiryo', sans-serif; background: #f5f5f5; color: #333; line-height: 1.6; }}
        .container {{ max-width: 960px; margin: 0 auto; padding: 24px; }}
        h1 {{ font-size: 28px; margin-bottom: 8px; color: #1a1a1a; }}
        h2 {{ font-size: 20px; margin: 24px 0 12px; color: #1a1a1a; border-bottom: 2px solid #e0e0e0; padding-bottom: 4px; }}
        .meta {{ color: #666; font-size: 14px; margin-bottom: 24px; }}
        .card {{ background: #fff; border-radius: 8px; padding: 20px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
        .stat-item {{ text-align: center; padding: 16px; background: #fafafa; border-radius: 6px; }}
        .stat-value {{ font-size: 32px; font-weight: bold; color: #1976D2; }}
        .stat-label {{ font-size: 13px; color: #666; margin-top: 4px; }}
        .progress-bar {{ background: #e0e0e0; border-radius: 10px; height: 20px; overflow: hidden; margin: 8px 0; }}
        .progress-fill {{ background: linear-gradient(90deg, #4CAF50, #66BB6A); height: 100%; border-radius: 10px; transition: width 0.3s; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #eee; font-size: 14px; }}
        th {{ background: #fafafa; font-weight: 600; color: #555; }}
        .footer {{ text-align: center; color: #999; font-size: 12px; margin-top: 32px; padding-top: 16px; border-top: 1px solid #e0e0e0; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{project_name}</h1>
        <div class="meta">
            ID: {project_id} &nbsp;|&nbsp; ステータス: {_status_badge(project_status)} &nbsp;|&nbsp; 作成日: {created_at}
        </div>

        <h2>プロジェクト統計</h2>
        <div class="card">
            <div class="stats">
                <div class="stat-item">
                    <div class="stat-value">{task_total}</div>
                    <div class="stat-label">タスク総数</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">{task_completed}</div>
                    <div class="stat-label">完了タスク</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">{progress_pct}%</div>
                    <div class="stat-label">進捗率</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">{len(orders)}</div>
                    <div class="stat-label">ORDER数</div>
                </div>
            </div>
            <div style="margin-top: 16px;">
                <div style="font-size: 13px; color: #666;">タスク進捗</div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {progress_pct}%;"></div>
                </div>
                <div style="font-size: 12px; color: #999;">
                    完了 {task_completed} / 進行中 {task_stats['in_progress']} / 保留 {task_stats['pending']} / 差戻 {task_stats['rejected']}
                </div>
            </div>
        </div>

        <h2>バックログ</h2>
        <div class="card">
            <div class="stats">
                <div class="stat-item">
                    <div class="stat-value">{backlog_stats['total']}</div>
                    <div class="stat-label">バックログ総数</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">{backlog_stats['todo']}</div>
                    <div class="stat-label">TODO</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">{backlog_stats['done']}</div>
                    <div class="stat-label">完了</div>
                </div>
            </div>
        </div>

        <h2>ORDER一覧（最新20件）</h2>
        <div class="card">
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>タイトル</th>
                        <th>ステータス</th>
                        <th>作成日</th>
                    </tr>
                </thead>
                <tbody>
                    {order_rows if order_rows else '<tr><td colspan="4" style="text-align:center;color:#999;">ORDERはまだありません</td></tr>'}
                </tbody>
            </table>
        </div>

        <div class="footer">
            AI PM Manager V2 - 生成日時: {generated_at}
        </div>
    </div>
</body>
</html>"""


def generate_project_page(
    project_id: str,
    *,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    プロジェクト紹介ページを生成

    Args:
        project_id: プロジェクトID
        db_path: データベースパス（テスト用）

    Returns:
        生成結果の辞書 {"success": bool, "html"?: str, "error"?: str}
    """
    try:
        validate_project_name(project_id)

        conn = get_connection(db_path=db_path)
        try:
            if not project_exists(conn, project_id):
                return {
                    "success": False,
                    "error": f"プロジェクトが見つかりません: {project_id}",
                }

            project = _get_project_info(conn, project_id)
            if project is None:
                return {
                    "success": False,
                    "error": f"プロジェクト情報の取得に失敗しました: {project_id}",
                }

            orders = _get_order_summary(conn, project_id)
            task_stats = _get_task_stats(conn, project_id)
            backlog_stats = _get_backlog_stats(conn, project_id)

            page_html = _build_html(project, orders, task_stats, backlog_stats)

            return {
                "success": True,
                "html": page_html,
            }
        finally:
            conn.close()

    except ValidationError as e:
        return {"success": False, "error": f"入力検証エラー: {e}"}
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
        description="プロジェクト紹介ページを生成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # JSON形式で生成結果を取得
  python generate_page.py ai_pm_manager_v2 --json

  # テキスト形式で確認
  python generate_page.py ai_pm_manager_v2
"""
    )

    parser.add_argument(
        "project_id",
        help="プロジェクトID（例: ai_pm_manager_v2）"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )

    try:
        args = parser.parse_args()
    except (SystemExit, argparse.ArgumentError) as e:
        error_msg = str(e) if str(e) else "引数エラー"
        print(json.dumps({
            "success": False,
            "error": f"引数エラー: {error_msg}",
        }, ensure_ascii=False))
        sys.exit(1)

    result = generate_project_page(project_id=args.project_id)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["success"]:
            print(result["html"])
        else:
            print(f"[ERROR] {result['error']}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
