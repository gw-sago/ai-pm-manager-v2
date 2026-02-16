#!/usr/bin/env python3
"""
AI PM Framework - 横断バックログ一覧取得スクリプト

Usage:
    python backend/xbacklog/list.py SUPERVISOR_ID [options]

Arguments:
    SUPERVISOR_ID       Supervisor ID（例: SUPERVISOR_001）

Options:
    --status STATUS     ステータスでフィルタ（PENDING/ANALYZING/ASSIGNED/DONE/CANCELED）
    --priority PRIORITY 優先度でフィルタ（High/Medium/Low）
    --json              JSON形式で出力

Example:
    python backend/xbacklog/list.py SUPERVISOR_001
    python backend/xbacklog/list.py SUPERVISOR_001 --status PENDING
    python backend/xbacklog/list.py SUPERVISOR_001 --json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import get_connection, fetch_all, fetch_one, DatabaseError
from utils.validation import ValidationError


# 有効なステータス値
VALID_STATUSES = ('PENDING', 'ANALYZING', 'ASSIGNED', 'DONE', 'CANCELED')

# 有効な優先度値
VALID_PRIORITIES = ('High', 'Medium', 'Low')


def list_xbacklog(
    supervisor_id: str,
    *,
    status: Optional[str] = None,
    priority: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    横断バックログ一覧を取得

    Args:
        supervisor_id: Supervisor ID
        status: ステータスでフィルタ（省略時は全件）
        priority: 優先度でフィルタ（省略時は全件）

    Returns:
        横断バックログ一覧
    """
    conn = get_connection()
    try:
        # Supervisor存在確認
        sv = fetch_one(
            conn,
            "SELECT id FROM supervisors WHERE id = ?",
            (supervisor_id,)
        )
        if not sv:
            raise ValidationError(f"Supervisor '{supervisor_id}' が見つかりません")

        # クエリ構築
        query = """
            SELECT
                x.id,
                x.supervisor_id,
                x.title,
                x.description,
                x.priority,
                x.status,
                x.assigned_project_id,
                x.assigned_backlog_id,
                x.created_at,
                x.updated_at,
                p.name as assigned_project_name
            FROM cross_project_backlog x
            LEFT JOIN projects p ON x.assigned_project_id = p.id
            WHERE x.supervisor_id = ?
        """
        params = [supervisor_id]

        if status:
            query += " AND x.status = ?"
            params.append(status)

        if priority:
            query += " AND x.priority = ?"
            params.append(priority)

        # ソート: ステータス順 → 優先度順 → 作成日順
        query += """
            ORDER BY
                CASE x.status
                    WHEN 'PENDING' THEN 1
                    WHEN 'ANALYZING' THEN 2
                    WHEN 'ASSIGNED' THEN 3
                    WHEN 'DONE' THEN 4
                    WHEN 'CANCELED' THEN 5
                END,
                CASE x.priority
                    WHEN 'High' THEN 1
                    WHEN 'Medium' THEN 2
                    WHEN 'Low' THEN 3
                END,
                x.created_at DESC
        """

        results = fetch_all(conn, query, tuple(params))
        return [dict(row) for row in results]

    finally:
        conn.close()


def main():
    """CLI エントリーポイント"""
    try:
        from config import setup_utf8_output
    except ImportError:
        from config import setup_utf8_output
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="横断バックログ一覧を取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("supervisor_id", help="Supervisor ID")
    parser.add_argument("--status", choices=VALID_STATUSES,
                        help="ステータスでフィルタ")
    parser.add_argument("--priority", choices=VALID_PRIORITIES,
                        help="優先度でフィルタ")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    try:
        items = list_xbacklog(
            args.supervisor_id,
            status=args.status,
            priority=args.priority,
        )

        if args.json:
            print(json.dumps(items, ensure_ascii=False, indent=2, default=str))
        else:
            if not items:
                print(f"Supervisor '{args.supervisor_id}' に横断バックログはありません。")
                return

            print(f"\n=== 横断バックログ一覧 ({len(items)}件) ===")
            print(f"Supervisor: {args.supervisor_id}\n")

            # ステータス別にグループ化して表示
            current_status = None
            for item in items:
                if item['status'] != current_status:
                    current_status = item['status']
                    status_label = {
                        'PENDING': '📋 未処理',
                        'ANALYZING': '🔍 分析中',
                        'ASSIGNED': '✅ 振り分け済',
                        'DONE': '✓ 完了',
                        'CANCELED': '✗ キャンセル'
                    }.get(current_status, current_status)
                    print(f"\n--- {status_label} ---")

                priority_mark = {'High': '🔴', 'Medium': '🟡', 'Low': '🟢'}.get(item['priority'], '')
                print(f"\n  {priority_mark} {item['id']}: {item['title']}")
                if item.get('description'):
                    print(f"    説明: {item['description'][:50]}...")
                print(f"    優先度: {item['priority']}")
                if item.get('assigned_project_id'):
                    print(f"    振り分け先: {item['assigned_project_id']} ({item.get('assigned_project_name', '')})")
                    if item.get('assigned_backlog_id'):
                        print(f"    BACKLOG: {item['assigned_backlog_id']}")

    except (ValidationError, DatabaseError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
