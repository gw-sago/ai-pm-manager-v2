#!/usr/bin/env python3
"""
AI PM Framework - Supervisorダッシュボードスクリプト

Usage:
    python backend/supervisor/dashboard.py SUPERVISOR_ID [options]

Arguments:
    SUPERVISOR_ID       Supervisor ID（例: SUPERVISOR_001）

Options:
    --json              JSON形式で出力

Example:
    python backend/supervisor/dashboard.py SUPERVISOR_001
    python backend/supervisor/dashboard.py SUPERVISOR_001 --json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, List

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import get_connection, fetch_one, fetch_all, DatabaseError
from utils.validation import ValidationError


def get_supervisor_dashboard(supervisor_id: str) -> Dict[str, Any]:
    """
    Supervisorダッシュボード情報を取得

    Args:
        supervisor_id: Supervisor ID

    Returns:
        ダッシュボード情報
    """
    conn = get_connection()
    try:
        # Supervisor情報
        supervisor = fetch_one(
            conn,
            "SELECT * FROM supervisors WHERE id = ?",
            (supervisor_id,)
        )

        if not supervisor:
            raise ValidationError(f"Supervisor '{supervisor_id}' が見つかりません")

        supervisor = dict(supervisor)

        # 配下プロジェクト情報
        projects = fetch_all(
            conn,
            """
            SELECT
                p.id,
                p.name,
                p.status,
                p.current_order_id,
                (SELECT COUNT(*) FROM orders o WHERE o.project_id = p.id) as total_orders,
                (SELECT COUNT(*) FROM orders o WHERE o.project_id = p.id AND o.status = 'COMPLETED') as completed_orders,
                (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id) as total_tasks,
                (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.status IN ('COMPLETED', 'SKIPPED')) as completed_tasks,
                (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.status = 'IN_PROGRESS') as in_progress_tasks
            FROM projects p
            WHERE p.supervisor_id = ?
            ORDER BY p.id
            """,
            (supervisor_id,)
        )
        projects = [dict(p) for p in projects]

        # 各プロジェクトの進捗率を計算
        for proj in projects:
            if proj['total_tasks'] > 0:
                proj['task_progress_percent'] = round(
                    proj['completed_tasks'] / proj['total_tasks'] * 100, 1
                )
            else:
                proj['task_progress_percent'] = 0

            if proj['total_orders'] > 0:
                proj['order_progress_percent'] = round(
                    proj['completed_orders'] / proj['total_orders'] * 100, 1
                )
            else:
                proj['order_progress_percent'] = 0

        # 横断バックログ集計
        xbacklog_summary = fetch_all(
            conn,
            """
            SELECT status, COUNT(*) as count
            FROM cross_project_backlog
            WHERE supervisor_id = ?
            GROUP BY status
            """,
            (supervisor_id,)
        )
        xbacklog_by_status = {row['status']: row['count'] for row in xbacklog_summary}

        # 横断バックログ詳細（直近の未処理分）
        pending_xbacklog = fetch_all(
            conn,
            """
            SELECT id, title, priority, status, created_at
            FROM cross_project_backlog
            WHERE supervisor_id = ? AND status IN ('PENDING', 'ANALYZING')
            ORDER BY
                CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 WHEN 'Low' THEN 3 END,
                created_at
            LIMIT 5
            """,
            (supervisor_id,)
        )
        pending_xbacklog = [dict(x) for x in pending_xbacklog]

        # 集計
        total_orders = sum(p['total_orders'] for p in projects)
        completed_orders = sum(p['completed_orders'] for p in projects)
        total_tasks = sum(p['total_tasks'] for p in projects)
        completed_tasks = sum(p['completed_tasks'] for p in projects)
        in_progress_tasks = sum(p['in_progress_tasks'] for p in projects)

        overall_progress = 0
        if total_tasks > 0:
            overall_progress = round(completed_tasks / total_tasks * 100, 1)

        total_xbacklog = sum(xbacklog_by_status.values())

        return {
            'supervisor_id': supervisor_id,
            'supervisor_name': supervisor['name'],
            'supervisor_status': supervisor['status'],
            'projects': projects,
            'project_count': len(projects),
            'xbacklog_summary': xbacklog_by_status,
            'xbacklog_total': total_xbacklog,
            'pending_xbacklog': pending_xbacklog,
            'summary': {
                'total_orders': total_orders,
                'completed_orders': completed_orders,
                'total_tasks': total_tasks,
                'completed_tasks': completed_tasks,
                'in_progress_tasks': in_progress_tasks,
                'overall_progress_percent': overall_progress
            }
        }

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
        description="Supervisorダッシュボードを表示",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("supervisor_id", help="Supervisor ID")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    try:
        dashboard = get_supervisor_dashboard(args.supervisor_id)

        if args.json:
            print(json.dumps(dashboard, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"\n{'=' * 60}")
            print(f"  Supervisor ダッシュボード")
            print(f"{'=' * 60}")
            print(f"\n  {dashboard['supervisor_id']}: {dashboard['supervisor_name']}")
            print(f"  ステータス: {dashboard['supervisor_status']}")

            # プロジェクト一覧
            print(f"\n{'─' * 60}")
            print(f"  ■ 配下プロジェクト ({dashboard['project_count']}件)")
            print(f"{'─' * 60}")

            if dashboard['projects']:
                print(f"\n  {'プロジェクト':<20} {'ステータス':<15} {'ORDER進捗':<12} {'タスク進捗':<12}")
                print(f"  {'-' * 20} {'-' * 15} {'-' * 12} {'-' * 12}")

                for proj in dashboard['projects']:
                    order_progress = f"{proj['completed_orders']}/{proj['total_orders']}"
                    task_progress = f"{proj['completed_tasks']}/{proj['total_tasks']}"
                    print(f"  {proj['id']:<20} {proj['status']:<15} {order_progress:<12} {task_progress:<12}")
            else:
                print("\n  (配下プロジェクトなし)")

            # 横断バックログ
            print(f"\n{'─' * 60}")
            print(f"  ■ 横断バックログ ({dashboard['xbacklog_total']}件)")
            print(f"{'─' * 60}")

            xb = dashboard['xbacklog_summary']
            print(f"\n  {'ステータス':<15} {'件数':<10}")
            print(f"  {'-' * 15} {'-' * 10}")
            for status in ['PENDING', 'ANALYZING', 'ASSIGNED', 'DONE', 'CANCELED']:
                count = xb.get(status, 0)
                if count > 0:
                    print(f"  {status:<15} {count:<10}")

            if dashboard['pending_xbacklog']:
                print(f"\n  --- 未処理バックログ（上位5件） ---")
                for xbacklog in dashboard['pending_xbacklog']:
                    priority_mark = {'High': '🔴', 'Medium': '🟡', 'Low': '🟢'}.get(xbacklog['priority'], '')
                    print(f"  {priority_mark} {xbacklog['id']}: {xbacklog['title'][:30]}")

            # 集計
            summary = dashboard['summary']
            print(f"\n{'─' * 60}")
            print(f"  ■ 集計")
            print(f"{'─' * 60}")
            print(f"\n  総ORDER数: {summary['total_orders']} (完了: {summary['completed_orders']})")
            print(f"  総タスク数: {summary['total_tasks']} (完了: {summary['completed_tasks']}, 進行中: {summary['in_progress_tasks']})")
            print(f"  全体進捗率: {summary['overall_progress_percent']}%")

            # プログレスバー
            progress = int(summary['overall_progress_percent'] / 10)
            bar = '█' * progress + '░' * (10 - progress)
            print(f"\n  [{bar}] {summary['overall_progress_percent']}%")

            print(f"\n{'=' * 60}\n")

    except (ValidationError, DatabaseError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
