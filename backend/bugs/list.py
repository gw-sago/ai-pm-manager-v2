#!/usr/bin/env python3
"""
AI PM Framework - Bug Pattern一覧表示スクリプト

Usage:
    python -m bugs.list [options]

Options:
    --project-id    プロジェクトID指定（省略時は全て表示）
    --generic       汎用パターンのみ表示（project_id=NULL）
    --status        ステータスフィルタ（ACTIVE/FIXED/ARCHIVED）
    --severity      深刻度フィルタ（Critical/High/Medium/Low）
    --pattern-type  パターン分類フィルタ
    --json          JSON形式で出力

Example:
    # 全バグパターン表示
    python -m bugs.list

    # 汎用パターンのみ表示
    python -m bugs.list --generic

    # プロジェクト固有パターン表示
    python -m bugs.list --project-id ai_pm_manager

    # ACTIVEな重大バグのみ
    python -m bugs.list --status ACTIVE --severity Critical
"""

import argparse
import json
import sys
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


def list_bugs(
    *,
    project_id: Optional[str] = None,
    generic: bool = False,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    pattern_type: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """
    バグパターン一覧を取得

    Args:
        project_id: プロジェクトID（指定時はそのプロジェクト固有のバグを表示）
        generic: Trueの場合、汎用パターン（project_id=NULL）のみ表示
        status: ステータスフィルタ
        severity: 深刻度フィルタ
        pattern_type: パターン分類フィルタ
        db_path: データベースパス（テスト用）

    Returns:
        バグパターンのリスト
    """
    try:
        conn = get_connection(db_path)

        # WHERE句を動的に構築
        conditions = []
        params = []

        if generic:
            conditions.append("project_id IS NULL")
        elif project_id:
            conditions.append("(project_id = ? OR project_id IS NULL)")
            params.append(project_id)

        if status:
            conditions.append("status = ?")
            params.append(status)

        if severity:
            conditions.append("severity = ?")
            params.append(severity)

        if pattern_type:
            conditions.append("pattern_type = ?")
            params.append(pattern_type)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query = f"""
            SELECT
                id, project_id, title, description, pattern_type,
                severity, status, solution, related_files, tags,
                occurrence_count, last_occurred_at,
                created_at, updated_at
            FROM bugs
            WHERE {where_clause}
            ORDER BY
                severity DESC,
                occurrence_count DESC,
                created_at DESC
        """

        rows = fetch_all(conn, query, tuple(params))
        conn.close()

        return rows_to_dicts(rows)

    except DatabaseError as e:
        print(f"[ERROR] データベースエラー: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}", file=sys.stderr)
        return []


def format_bug_summary(bug: Dict[str, Any]) -> str:
    """
    バグ情報を要約形式でフォーマット

    Args:
        bug: バグ情報

    Returns:
        フォーマットされた文字列
    """
    scope = "汎用" if bug.get("project_id") is None else f"固有({bug['project_id']})"
    pattern = f" [{bug['pattern_type']}]" if bug.get("pattern_type") else ""

    lines = [
        f"■ {bug['id']}{pattern} - {bug['title']}",
        f"  深刻度: {bug['severity']} | ステータス: {bug['status']} | スコープ: {scope}",
    ]

    if bug.get("occurrence_count", 0) > 1:
        lines.append(f"  発生回数: {bug['occurrence_count']}回")

    if bug.get("tags"):
        lines.append(f"  タグ: {bug['tags']}")

    # 説明を短く表示（最初の100文字）
    desc = bug.get("description", "")
    if len(desc) > 100:
        desc = desc[:100] + "..."
    lines.append(f"  説明: {desc}")

    if bug.get("solution"):
        solution = bug["solution"]
        if len(solution) > 100:
            solution = solution[:100] + "..."
        lines.append(f"  解決策: {solution}")

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
        description="バグパターン一覧を表示",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 全バグパターン表示
  python list.py

  # 汎用パターンのみ表示
  python list.py --generic

  # プロジェクト固有パターン表示（汎用パターンも含む）
  python list.py --project-id ai_pm_manager

  # ACTIVEな重大バグのみ
  python list.py --status ACTIVE --severity Critical
"""
    )

    parser.add_argument(
        "--project-id", "-p",
        help="プロジェクトID（指定時はそのプロジェクト固有+汎用パターンを表示）"
    )
    parser.add_argument(
        "--generic", "-g",
        action="store_true",
        help="汎用パターンのみ表示（project_id=NULL）"
    )
    parser.add_argument(
        "--status", "-s",
        choices=["ACTIVE", "FIXED", "ARCHIVED"],
        help="ステータスフィルタ"
    )
    parser.add_argument(
        "--severity",
        choices=["Critical", "High", "Medium", "Low"],
        help="深刻度フィルタ"
    )
    parser.add_argument(
        "--pattern-type",
        help="パターン分類フィルタ"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )

    args = parser.parse_args()

    bugs = list_bugs(
        project_id=args.project_id,
        generic=args.generic,
        status=args.status,
        severity=args.severity,
        pattern_type=args.pattern_type,
    )

    if args.json:
        print(json.dumps(bugs, ensure_ascii=False, indent=2))
    else:
        if not bugs:
            print("[INFO] バグパターンが見つかりませんでした")
            return

        print(f"[INFO] バグパターン一覧 (全{len(bugs)}件)\n")

        for bug in bugs:
            print(format_bug_summary(bug))
            print()


if __name__ == "__main__":
    main()
