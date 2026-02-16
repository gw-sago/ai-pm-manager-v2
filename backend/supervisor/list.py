#!/usr/bin/env python3
"""
AI PM Framework - Supervisor一覧取得スクリプト

Usage:
    python backend/supervisor/list.py [options]

Options:
    --status STATUS     ステータスでフィルタ（ACTIVE/INACTIVE）
    --with-projects     配下プロジェクト情報を含める
    --json              JSON形式で出力

Example:
    python backend/supervisor/list.py
    python backend/supervisor/list.py --status ACTIVE
    python backend/supervisor/list.py --with-projects --json
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

from utils.db import get_connection, fetch_all, DatabaseError


def list_supervisors(
    *,
    status: Optional[str] = None,
    with_projects: bool = False,
) -> List[Dict[str, Any]]:
    """
    Supervisor一覧を取得

    Args:
        status: ステータスでフィルタ（省略時は全件）
        with_projects: 配下プロジェクト情報を含めるか

    Returns:
        Supervisor一覧
    """
    conn = get_connection()
    try:
        # 基本クエリ
        query = """
            SELECT
                s.id,
                s.name,
                s.description,
                s.status,
                s.created_at,
                s.updated_at,
                (SELECT COUNT(*) FROM projects p WHERE p.supervisor_id = s.id) as project_count
            FROM supervisors s
        """
        params = []

        # ステータスフィルタ
        if status:
            query += " WHERE s.status = ?"
            params.append(status)

        query += " ORDER BY s.id"

        results = fetch_all(conn, query, tuple(params))

        supervisors = [dict(row) for row in results]

        # プロジェクト情報を追加
        if with_projects:
            for supervisor in supervisors:
                projects = fetch_all(
                    conn,
                    """
                    SELECT id, name, status
                    FROM projects
                    WHERE supervisor_id = ?
                    ORDER BY id
                    """,
                    (supervisor['id'],)
                )
                supervisor['projects'] = [dict(p) for p in projects]

        return supervisors

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
        description="Supervisor一覧を取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("--status", choices=['ACTIVE', 'INACTIVE'],
                        help="ステータスでフィルタ")
    parser.add_argument("--with-projects", action="store_true",
                        help="配下プロジェクト情報を含める")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    try:
        supervisors = list_supervisors(
            status=args.status,
            with_projects=args.with_projects,
        )

        if args.json:
            print(json.dumps(supervisors, ensure_ascii=False, indent=2, default=str))
        else:
            if not supervisors:
                print("Supervisorが登録されていません。")
                return

            print(f"\n=== Supervisor一覧 ({len(supervisors)}件) ===\n")

            for sv in supervisors:
                status_mark = "●" if sv['status'] == 'ACTIVE' else "○"
                print(f"{status_mark} {sv['id']}: {sv['name']}")
                if sv.get('description'):
                    print(f"  説明: {sv['description']}")
                print(f"  ステータス: {sv['status']}")
                print(f"  配下プロジェクト数: {sv['project_count']}")

                if args.with_projects and sv.get('projects'):
                    print("  配下プロジェクト:")
                    for proj in sv['projects']:
                        print(f"    - {proj['id']}: {proj['name']} ({proj['status']})")

                print()

    except DatabaseError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
