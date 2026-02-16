#!/usr/bin/env python3
"""
AI PM Framework - 横断バックログ詳細取得スクリプト

Usage:
    python backend/xbacklog/get.py XBACKLOG_ID [options]

Arguments:
    XBACKLOG_ID         横断バックログID（例: XBACKLOG_001）

Options:
    --json              JSON形式で出力

Example:
    python backend/xbacklog/get.py XBACKLOG_001
    python backend/xbacklog/get.py XBACKLOG_001 --json
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

from utils.db import get_connection, fetch_one, DatabaseError
from utils.validation import ValidationError


def get_xbacklog(xbacklog_id: str) -> Optional[Dict[str, Any]]:
    """
    横断バックログ詳細を取得

    Args:
        xbacklog_id: 横断バックログID

    Returns:
        横断バックログ情報（存在しない場合はNone）
    """
    conn = get_connection()
    try:
        result = fetch_one(
            conn,
            """
            SELECT
                x.id,
                x.supervisor_id,
                x.title,
                x.description,
                x.priority,
                x.status,
                x.assigned_project_id,
                x.assigned_backlog_id,
                x.analysis_result,
                x.created_at,
                x.updated_at,
                s.name as supervisor_name,
                p.name as assigned_project_name
            FROM cross_project_backlog x
            JOIN supervisors s ON x.supervisor_id = s.id
            LEFT JOIN projects p ON x.assigned_project_id = p.id
            WHERE x.id = ?
            """,
            (xbacklog_id,)
        )

        if result:
            data = dict(result)
            # analysis_resultをJSONパース
            if data.get('analysis_result'):
                try:
                    data['analysis_result'] = json.loads(data['analysis_result'])
                except json.JSONDecodeError:
                    pass  # パース失敗時はそのまま文字列
            return data

        return None

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
        description="横断バックログ詳細を取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("xbacklog_id", help="横断バックログID")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    try:
        xbacklog = get_xbacklog(args.xbacklog_id)

        if not xbacklog:
            print(f"エラー: 横断バックログ '{args.xbacklog_id}' が見つかりません", file=sys.stderr)
            sys.exit(1)

        if args.json:
            print(json.dumps(xbacklog, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"\n=== 横断バックログ詳細: {xbacklog['id']} ===\n")

            status_label = {
                'PENDING': '📋 未処理',
                'ANALYZING': '🔍 分析中',
                'ASSIGNED': '✅ 振り分け済',
                'DONE': '✓ 完了',
                'CANCELED': '✗ キャンセル'
            }.get(xbacklog['status'], xbacklog['status'])

            priority_mark = {'High': '🔴', 'Medium': '🟡', 'Low': '🟢'}.get(xbacklog['priority'], '')

            print(f"タイトル: {xbacklog['title']}")
            if xbacklog.get('description'):
                print(f"説明: {xbacklog['description']}")
            print(f"優先度: {priority_mark} {xbacklog['priority']}")
            print(f"ステータス: {status_label}")
            print(f"\nSupervisor: {xbacklog['supervisor_id']} ({xbacklog['supervisor_name']})")

            if xbacklog.get('assigned_project_id'):
                print(f"\n--- 振り分け情報 ---")
                print(f"プロジェクト: {xbacklog['assigned_project_id']} ({xbacklog.get('assigned_project_name', '')})")
                if xbacklog.get('assigned_backlog_id'):
                    print(f"BACKLOG: {xbacklog['assigned_backlog_id']}")

            if xbacklog.get('analysis_result'):
                print(f"\n--- 分析結果 ---")
                if isinstance(xbacklog['analysis_result'], dict):
                    for key, value in xbacklog['analysis_result'].items():
                        print(f"  {key}: {value}")
                else:
                    print(f"  {xbacklog['analysis_result']}")

            print(f"\n作成日時: {xbacklog['created_at']}")
            print(f"更新日時: {xbacklog['updated_at']}")

    except (ValidationError, DatabaseError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
