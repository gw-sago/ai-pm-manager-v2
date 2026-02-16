#!/usr/bin/env python3
"""
AI PM Framework - Supervisor更新スクリプト

Usage:
    python backend/supervisor/update.py SUPERVISOR_ID [options]

Arguments:
    SUPERVISOR_ID       Supervisor ID（例: SUPERVISOR_001）

Options:
    --name NAME         Supervisor名を変更
    --desc DESCRIPTION  説明を変更
    --status STATUS     ステータスを変更（ACTIVE/INACTIVE）
    --json              JSON形式で出力

Example:
    python backend/supervisor/update.py SUPERVISOR_001 --name "新しい名前"
    python backend/supervisor/update.py SUPERVISOR_001 --status INACTIVE
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import get_connection, execute_query, fetch_one, DatabaseError
from utils.validation import ValidationError


# 有効なステータス値
VALID_STATUSES = ('ACTIVE', 'INACTIVE')


def update_supervisor(
    supervisor_id: str,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Supervisorを更新

    Args:
        supervisor_id: Supervisor ID
        name: 新しい名前（省略時は変更なし）
        description: 新しい説明（省略時は変更なし）
        status: 新しいステータス（省略時は変更なし）

    Returns:
        更新後のSupervisor情報

    Raises:
        ValidationError: 入力検証エラー
        DatabaseError: DB操作エラー
    """
    # 存在確認
    conn = get_connection()
    try:
        existing = fetch_one(
            conn,
            "SELECT * FROM supervisors WHERE id = ?",
            (supervisor_id,)
        )

        if not existing:
            raise ValidationError(f"Supervisor '{supervisor_id}' が見つかりません")

        # 更新フィールドを構築
        updates = []
        params = []

        if name is not None:
            if not name:
                raise ValidationError("名前を空にすることはできません")
            updates.append("name = ?")
            params.append(name)

        if description is not None:
            updates.append("description = ?")
            params.append(description if description else None)

        if status is not None:
            if status not in VALID_STATUSES:
                raise ValidationError(
                    f"無効なステータス: {status}. "
                    f"有効な値: {', '.join(VALID_STATUSES)}"
                )
            updates.append("status = ?")
            params.append(status)

        if not updates:
            raise ValidationError("更新するフィールドが指定されていません")

        # updated_atを追加
        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())

        # パラメータにIDを追加
        params.append(supervisor_id)

        # 更新実行
        query = f"UPDATE supervisors SET {', '.join(updates)} WHERE id = ?"
        execute_query(conn, query, tuple(params))
        conn.commit()

        # 更新後のデータを取得
        result = fetch_one(
            conn,
            """
            SELECT id, name, description, status, created_at, updated_at
            FROM supervisors WHERE id = ?
            """,
            (supervisor_id,)
        )

        return dict(result) if result else {}

    except Exception as e:
        conn.rollback()
        if isinstance(e, ValidationError):
            raise
        raise DatabaseError(f"Supervisor更新エラー: {e}")
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
        description="Supervisorを更新",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("supervisor_id", help="Supervisor ID")
    parser.add_argument("--name", help="新しい名前")
    parser.add_argument("--desc", dest="description", help="新しい説明")
    parser.add_argument("--status", choices=VALID_STATUSES,
                        help="新しいステータス")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    # 更新対象がなければエラー
    if args.name is None and args.description is None and args.status is None:
        parser.error("--name, --desc, --status のいずれかを指定してください")

    try:
        supervisor = update_supervisor(
            args.supervisor_id,
            name=args.name,
            description=args.description,
            status=args.status,
        )

        if args.json:
            print(json.dumps(supervisor, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"Supervisor '{args.supervisor_id}' を更新しました。")
            print(f"  名前: {supervisor['name']}")
            if supervisor.get('description'):
                print(f"  説明: {supervisor['description']}")
            print(f"  ステータス: {supervisor['status']}")

    except (ValidationError, DatabaseError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
