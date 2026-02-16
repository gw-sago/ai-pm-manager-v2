#!/usr/bin/env python3
"""
AI PM Framework - Supervisor作成スクリプト

Usage:
    python backend/supervisor/create.py SUPERVISOR_ID [options]

Arguments:
    SUPERVISOR_ID       Supervisor ID（例: SUPERVISOR_001）

Options:
    --name NAME         Supervisor名（必須）
    --desc DESCRIPTION  説明（任意）
    --status STATUS     ステータス（ACTIVE/INACTIVE、デフォルト: ACTIVE）
    --json              JSON形式で出力

Example:
    python backend/supervisor/create.py SUPERVISOR_001 --name "フロントエンド統括"
    python backend/supervisor/create.py SUPERVISOR_002 --name "バックエンド統括" --desc "API・DB関連"
"""

import argparse
import json
import re
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

# Supervisor IDのパターン
SUPERVISOR_ID_PATTERN = re.compile(r'^SUPERVISOR_\d{3}$')


def validate_supervisor_id(supervisor_id: str) -> None:
    """Supervisor IDを検証"""
    if not supervisor_id:
        raise ValidationError("Supervisor IDは必須です")

    if not SUPERVISOR_ID_PATTERN.match(supervisor_id):
        raise ValidationError(
            f"Supervisor IDの形式が不正です: {supervisor_id}. "
            "形式: SUPERVISOR_XXX（XXXは3桁の数字）"
        )


def validate_status(status: str) -> None:
    """ステータスを検証"""
    if status not in VALID_STATUSES:
        raise ValidationError(
            f"無効なステータス: {status}. "
            f"有効な値: {', '.join(VALID_STATUSES)}"
        )


def supervisor_exists(supervisor_id: str) -> bool:
    """
    SupervisorがDBに存在するか確認

    Args:
        supervisor_id: Supervisor ID

    Returns:
        存在する場合True
    """
    conn = get_connection()
    try:
        result = fetch_one(
            conn,
            "SELECT id FROM supervisors WHERE id = ?",
            (supervisor_id,)
        )
        return result is not None
    finally:
        conn.close()


def get_next_supervisor_id() -> str:
    """
    次のSupervisor IDを取得

    Returns:
        次のSupervisor ID（例: SUPERVISOR_001）
    """
    conn = get_connection()
    try:
        result = fetch_one(
            conn,
            """
            SELECT id FROM supervisors
            WHERE id LIKE 'SUPERVISOR_%'
            ORDER BY id DESC LIMIT 1
            """
        )

        if result:
            # 現在の最大番号を取得して+1
            current_num = int(result['id'].split('_')[1])
            return f"SUPERVISOR_{current_num + 1:03d}"
        else:
            return "SUPERVISOR_001"
    finally:
        conn.close()


def create_supervisor(
    supervisor_id: Optional[str] = None,
    *,
    name: str,
    description: Optional[str] = None,
    status: str = "ACTIVE",
) -> Dict[str, Any]:
    """
    SupervisorをDBに作成

    Args:
        supervisor_id: Supervisor ID（省略時は自動採番）
        name: Supervisor名（必須）
        description: 説明（任意）
        status: ステータス（デフォルト: ACTIVE）

    Returns:
        作成されたSupervisor情報

    Raises:
        ValidationError: 入力検証エラー
        DatabaseError: DB操作エラー
    """
    # 自動採番
    if supervisor_id is None:
        supervisor_id = get_next_supervisor_id()

    # バリデーション
    validate_supervisor_id(supervisor_id)
    validate_status(status)

    if not name:
        raise ValidationError("Supervisor名は必須です")

    # 重複チェック
    if supervisor_exists(supervisor_id):
        raise ValidationError(f"Supervisor '{supervisor_id}' は既に存在します")

    now = datetime.now().isoformat()

    conn = get_connection()
    try:
        execute_query(
            conn,
            """
            INSERT INTO supervisors (id, name, description, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (supervisor_id, name, description, status, now, now)
        )
        conn.commit()

        # 作成したSupervisorを取得して返す
        result = fetch_one(
            conn,
            """
            SELECT id, name, description, status, created_at, updated_at
            FROM supervisors WHERE id = ?
            """,
            (supervisor_id,)
        )

        if result:
            return dict(result)
        else:
            raise DatabaseError("Supervisorの作成に失敗しました")

    except Exception as e:
        conn.rollback()
        if "UNIQUE constraint failed" in str(e):
            raise ValidationError(f"Supervisor '{supervisor_id}' は既に存在します")
        raise DatabaseError(f"Supervisor作成エラー: {e}")
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
        description="SupervisorをDBに作成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("supervisor_id", nargs="?", help="Supervisor ID（省略時は自動採番）")
    parser.add_argument("--name", required=True, help="Supervisor名（必須）")
    parser.add_argument("--desc", dest="description", help="説明（任意）")
    parser.add_argument("--status", default="ACTIVE",
                        choices=VALID_STATUSES,
                        help="ステータス（デフォルト: ACTIVE）")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    try:
        supervisor = create_supervisor(
            args.supervisor_id,
            name=args.name,
            description=args.description,
            status=args.status,
        )

        if args.json:
            print(json.dumps(supervisor, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"Supervisor '{supervisor['id']}' を作成しました。")
            print(f"  ID: {supervisor['id']}")
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
