#!/usr/bin/env python3
"""
AI PM Framework - Supervisor詳細取得スクリプト

Usage:
    python backend/supervisor/get.py SUPERVISOR_ID [options]

Arguments:
    SUPERVISOR_ID       Supervisor ID（例: SUPERVISOR_001）

Options:
    --with-projects     配下プロジェクト情報を含める
    --with-xbacklog     横断バックログ情報を含める
    --json              JSON形式で出力

Example:
    python backend/supervisor/get.py SUPERVISOR_001
    python backend/supervisor/get.py SUPERVISOR_001 --with-projects --json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import get_connection, fetch_one, fetch_all, DatabaseError
from utils.validation import ValidationError


def get_supervisor(
    supervisor_id: str,
    *,
    with_projects: bool = False,
    with_xbacklog: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Supervisor詳細を取得

    Args:
        supervisor_id: Supervisor ID
        with_projects: 配下プロジェクト情報を含めるか
        with_xbacklog: 横断バックログ情報を含めるか

    Returns:
        Supervisor情報（存在しない場合はNone）
    """
    conn = get_connection()
    try:
        # Supervisor基本情報
        result = fetch_one(
            conn,
            """
            SELECT
                s.id,
                s.name,
                s.description,
                s.status,
                s.created_at,
                s.updated_at,
                (SELECT COUNT(*) FROM projects p WHERE p.supervisor_id = s.id) as project_count,
                (SELECT COUNT(*) FROM cross_project_backlog x WHERE x.supervisor_id = s.id) as xbacklog_count
            FROM supervisors s
            WHERE s.id = ?
            """,
            (supervisor_id,)
        )

        if not result:
            return None

        supervisor = dict(result)

        # プロジェクト情報を追加
        if with_projects:
            projects = fetch_all(
                conn,
                """
                SELECT
                    p.id,
                    p.name,
                    p.status,
                    p.current_order_id,
                    (SELECT COUNT(*) FROM orders o WHERE o.project_id = p.id) as order_count,
                    (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.status NOT IN ('COMPLETED', 'CANCELLED', 'SKIPPED')) as active_task_count
                FROM projects p
                WHERE p.supervisor_id = ?
                ORDER BY p.id
                """,
                (supervisor_id,)
            )
            supervisor['projects'] = [dict(p) for p in projects]

        # 横断バックログ情報を追加
        if with_xbacklog:
            xbacklog = fetch_all(
                conn,
                """
                SELECT
                    id,
                    title,
                    priority,
                    status,
                    assigned_project_id,
                    assigned_backlog_id,
                    created_at
                FROM cross_project_backlog
                WHERE supervisor_id = ?
                ORDER BY
                    CASE status
                        WHEN 'PENDING' THEN 1
                        WHEN 'ANALYZING' THEN 2
                        WHEN 'ASSIGNED' THEN 3
                        WHEN 'DONE' THEN 4
                        ELSE 5
                    END,
                    CASE priority
                        WHEN 'High' THEN 1
                        WHEN 'Medium' THEN 2
                        WHEN 'Low' THEN 3
                    END
                """,
                (supervisor_id,)
            )
            supervisor['cross_project_backlog'] = [dict(x) for x in xbacklog]

        return supervisor

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
        description="Supervisor詳細を取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("supervisor_id", help="Supervisor ID")
    parser.add_argument("--with-projects", action="store_true",
                        help="配下プロジェクト情報を含める")
    parser.add_argument("--with-xbacklog", action="store_true",
                        help="横断バックログ情報を含める")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    try:
        supervisor = get_supervisor(
            args.supervisor_id,
            with_projects=args.with_projects,
            with_xbacklog=args.with_xbacklog,
        )

        if not supervisor:
            print(f"エラー: Supervisor '{args.supervisor_id}' が見つかりません", file=sys.stderr)
            sys.exit(1)

        if args.json:
            print(json.dumps(supervisor, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"\n=== Supervisor詳細: {supervisor['id']} ===\n")
            print(f"名前: {supervisor['name']}")
            if supervisor.get('description'):
                print(f"説明: {supervisor['description']}")
            print(f"ステータス: {supervisor['status']}")
            print(f"配下プロジェクト数: {supervisor['project_count']}")
            print(f"横断バックログ数: {supervisor['xbacklog_count']}")
            print(f"作成日時: {supervisor['created_at']}")
            print(f"更新日時: {supervisor['updated_at']}")

            if args.with_projects and supervisor.get('projects'):
                print(f"\n--- 配下プロジェクト ({len(supervisor['projects'])}件) ---")
                for proj in supervisor['projects']:
                    print(f"\n  {proj['id']}: {proj['name']}")
                    print(f"    ステータス: {proj['status']}")
                    if proj.get('current_order_id'):
                        print(f"    現在ORDER: {proj['current_order_id']}")
                    print(f"    ORDER数: {proj['order_count']}")
                    print(f"    アクティブタスク数: {proj['active_task_count']}")

            if args.with_xbacklog and supervisor.get('cross_project_backlog'):
                print(f"\n--- 横断バックログ ({len(supervisor['cross_project_backlog'])}件) ---")
                for xb in supervisor['cross_project_backlog']:
                    status_mark = {
                        'PENDING': '📋',
                        'ANALYZING': '🔍',
                        'ASSIGNED': '✅',
                        'DONE': '✓',
                        'CANCELED': '✗'
                    }.get(xb['status'], '?')
                    print(f"\n  {status_mark} {xb['id']}: {xb['title']}")
                    print(f"    優先度: {xb['priority']} | ステータス: {xb['status']}")
                    if xb.get('assigned_project_id'):
                        print(f"    振り分け先: {xb['assigned_project_id']} → {xb.get('assigned_backlog_id', '未作成')}")

    except DatabaseError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
