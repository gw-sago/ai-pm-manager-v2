#!/usr/bin/env python3
"""
AI PM Framework - Supervisor削除スクリプト

Usage:
    python backend/supervisor/delete.py SUPERVISOR_ID [options]

Arguments:
    SUPERVISOR_ID       Supervisor ID（例: SUPERVISOR_001）

Options:
    --force             確認なしで削除
    --json              JSON形式で出力

Note:
    - 配下プロジェクトのsupervisor_idはNULLに更新されます
    - 横断バックログはCASCADE削除されます

Example:
    python backend/supervisor/delete.py SUPERVISOR_001
    python backend/supervisor/delete.py SUPERVISOR_001 --force
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import get_connection, execute_query, fetch_one, fetch_all, DatabaseError
from utils.validation import ValidationError


def get_supervisor_info(supervisor_id: str) -> Dict[str, Any]:
    """
    削除対象Supervisorの情報を取得

    Args:
        supervisor_id: Supervisor ID

    Returns:
        Supervisor情報と関連データ
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
            return None

        result = dict(supervisor)

        # 配下プロジェクト
        projects = fetch_all(
            conn,
            "SELECT id, name FROM projects WHERE supervisor_id = ?",
            (supervisor_id,)
        )
        result['projects'] = [dict(p) for p in projects]

        # 横断バックログ
        xbacklog = fetch_all(
            conn,
            "SELECT id, title, status FROM cross_project_backlog WHERE supervisor_id = ?",
            (supervisor_id,)
        )
        result['cross_project_backlog'] = [dict(x) for x in xbacklog]

        return result

    finally:
        conn.close()


def delete_supervisor(supervisor_id: str) -> Dict[str, Any]:
    """
    Supervisorを削除

    Args:
        supervisor_id: Supervisor ID

    Returns:
        削除結果

    Raises:
        ValidationError: 入力検証エラー
        DatabaseError: DB操作エラー
    """
    conn = get_connection()
    try:
        # 存在確認と情報取得
        supervisor = fetch_one(
            conn,
            "SELECT id, name FROM supervisors WHERE id = ?",
            (supervisor_id,)
        )

        if not supervisor:
            raise ValidationError(f"Supervisor '{supervisor_id}' が見つかりません")

        # 配下プロジェクトのsupervisor_idをNULLに更新
        execute_query(
            conn,
            "UPDATE projects SET supervisor_id = NULL WHERE supervisor_id = ?",
            (supervisor_id,)
        )

        # 横断バックログはCASCADE削除される（FK設定）
        # 念のため明示的に削除
        xbacklog_result = execute_query(
            conn,
            "DELETE FROM cross_project_backlog WHERE supervisor_id = ?",
            (supervisor_id,)
        )

        # Supervisor削除
        execute_query(
            conn,
            "DELETE FROM supervisors WHERE id = ?",
            (supervisor_id,)
        )

        conn.commit()

        return {
            'deleted_supervisor_id': supervisor_id,
            'deleted_supervisor_name': supervisor['name'],
            'unassigned_projects': conn.total_changes,
            'success': True
        }

    except Exception as e:
        conn.rollback()
        if isinstance(e, ValidationError):
            raise
        raise DatabaseError(f"Supervisor削除エラー: {e}")
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
        description="Supervisorを削除",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("supervisor_id", help="Supervisor ID")
    parser.add_argument("--force", action="store_true", help="確認なしで削除")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    try:
        # 削除対象の情報を取得
        info = get_supervisor_info(args.supervisor_id)

        if not info:
            print(f"エラー: Supervisor '{args.supervisor_id}' が見つかりません", file=sys.stderr)
            sys.exit(1)

        # 確認表示
        if not args.force:
            print(f"\n=== 削除対象: {info['id']} ===")
            print(f"名前: {info['name']}")
            print(f"配下プロジェクト: {len(info['projects'])}件")
            for p in info['projects']:
                print(f"  - {p['id']}: {p['name']}")
            print(f"横断バックログ: {len(info['cross_project_backlog'])}件")
            for x in info['cross_project_backlog']:
                print(f"  - {x['id']}: {x['title']} ({x['status']})")

            print("\n※ 配下プロジェクトのsupervisor_idはNULLに更新されます")
            print("※ 横断バックログは削除されます")

            response = input("\n削除しますか？ [y/N]: ")
            if response.lower() != 'y':
                print("削除をキャンセルしました。")
                sys.exit(0)

        # 削除実行
        result = delete_supervisor(args.supervisor_id)

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"\nSupervisor '{args.supervisor_id}' を削除しました。")

    except (ValidationError, DatabaseError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
