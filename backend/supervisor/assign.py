#!/usr/bin/env python3
"""
AI PM Framework - プロジェクトSupervisor割当スクリプト

Usage:
    python backend/supervisor/assign.py PROJECT_ID SUPERVISOR_ID [options]

Arguments:
    PROJECT_ID          プロジェクトID
    SUPERVISOR_ID       Supervisor ID

Options:
    --json              JSON形式で出力

Example:
    python backend/supervisor/assign.py AI_PM_PJ SUPERVISOR_001
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import get_connection, execute_query, fetch_one, DatabaseError
from utils.validation import ValidationError


def assign_project_to_supervisor(
    project_id: str,
    supervisor_id: str,
) -> Dict[str, Any]:
    """
    プロジェクトをSupervisorに割り当て

    Args:
        project_id: プロジェクトID
        supervisor_id: Supervisor ID

    Returns:
        更新後のプロジェクト情報

    Raises:
        ValidationError: 入力検証エラー
        DatabaseError: DB操作エラー
    """
    conn = get_connection()
    try:
        # プロジェクト存在確認
        project = fetch_one(
            conn,
            "SELECT id, name, supervisor_id FROM projects WHERE id = ?",
            (project_id,)
        )
        if not project:
            raise ValidationError(f"プロジェクト '{project_id}' が見つかりません")

        # Supervisor存在確認
        supervisor = fetch_one(
            conn,
            "SELECT id, name, status FROM supervisors WHERE id = ?",
            (supervisor_id,)
        )
        if not supervisor:
            raise ValidationError(f"Supervisor '{supervisor_id}' が見つかりません")

        if supervisor['status'] != 'ACTIVE':
            raise ValidationError(f"Supervisor '{supervisor_id}' は非アクティブです")

        # 既に同じSupervisorに割り当て済みの場合
        if project['supervisor_id'] == supervisor_id:
            raise ValidationError(
                f"プロジェクト '{project_id}' は既に Supervisor '{supervisor_id}' に割り当て済みです"
            )

        # 割り当て実行
        execute_query(
            conn,
            """
            UPDATE projects
            SET supervisor_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (supervisor_id, datetime.now().isoformat(), project_id)
        )
        conn.commit()

        # 更新後のデータを取得
        result = fetch_one(
            conn,
            """
            SELECT p.id, p.name, p.status, p.supervisor_id, s.name as supervisor_name
            FROM projects p
            LEFT JOIN supervisors s ON p.supervisor_id = s.id
            WHERE p.id = ?
            """,
            (project_id,)
        )

        return {
            'success': True,
            'project_id': result['id'],
            'project_name': result['name'],
            'supervisor_id': result['supervisor_id'],
            'supervisor_name': result['supervisor_name'],
            'previous_supervisor_id': project['supervisor_id'],
            'message': f"プロジェクト '{project_id}' を Supervisor '{supervisor_id}' に割り当てました"
        }

    except Exception as e:
        conn.rollback()
        if isinstance(e, ValidationError):
            raise
        raise DatabaseError(f"プロジェクト割り当てエラー: {e}")
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
        description="プロジェクトをSupervisorに割り当て",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("supervisor_id", help="Supervisor ID")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    try:
        result = assign_project_to_supervisor(
            args.project_id,
            args.supervisor_id,
        )

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(result['message'])
            if result.get('previous_supervisor_id'):
                print(f"  (以前の割り当て: {result['previous_supervisor_id']})")

    except (ValidationError, DatabaseError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
