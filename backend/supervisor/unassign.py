#!/usr/bin/env python3
"""
AI PM Framework - プロジェクトSupervisor割当解除スクリプト

Usage:
    python backend/supervisor/unassign.py PROJECT_ID [options]

Arguments:
    PROJECT_ID          プロジェクトID

Options:
    --json              JSON形式で出力

Example:
    python backend/supervisor/unassign.py AI_PM_PJ
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


def unassign_project_from_supervisor(project_id: str) -> Dict[str, Any]:
    """
    プロジェクトのSupervisor割り当てを解除

    Args:
        project_id: プロジェクトID

    Returns:
        更新結果

    Raises:
        ValidationError: 入力検証エラー
        DatabaseError: DB操作エラー
    """
    conn = get_connection()
    try:
        # プロジェクト存在確認
        project = fetch_one(
            conn,
            """
            SELECT p.id, p.name, p.supervisor_id, s.name as supervisor_name
            FROM projects p
            LEFT JOIN supervisors s ON p.supervisor_id = s.id
            WHERE p.id = ?
            """,
            (project_id,)
        )
        if not project:
            raise ValidationError(f"プロジェクト '{project_id}' が見つかりません")

        # 既に割り当てがない場合
        if project['supervisor_id'] is None:
            raise ValidationError(
                f"プロジェクト '{project_id}' はSupervisorに割り当てられていません"
            )

        previous_supervisor_id = project['supervisor_id']
        previous_supervisor_name = project['supervisor_name']

        # 割り当て解除
        execute_query(
            conn,
            """
            UPDATE projects
            SET supervisor_id = NULL, updated_at = ?
            WHERE id = ?
            """,
            (datetime.now().isoformat(), project_id)
        )
        conn.commit()

        return {
            'success': True,
            'project_id': project_id,
            'project_name': project['name'],
            'previous_supervisor_id': previous_supervisor_id,
            'previous_supervisor_name': previous_supervisor_name,
            'message': f"プロジェクト '{project_id}' の Supervisor 割り当てを解除しました"
        }

    except Exception as e:
        conn.rollback()
        if isinstance(e, ValidationError):
            raise
        raise DatabaseError(f"割り当て解除エラー: {e}")
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
        description="プロジェクトのSupervisor割り当てを解除",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    try:
        result = unassign_project_from_supervisor(args.project_id)

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(result['message'])
            print(f"  (解除したSupervisor: {result['previous_supervisor_name']})")

    except (ValidationError, DatabaseError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
