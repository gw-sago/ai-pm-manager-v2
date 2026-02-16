#!/usr/bin/env python3
"""
AI PM Framework - 横断バックログ追加スクリプト

Usage:
    python backend/xbacklog/add.py SUPERVISOR_ID [options]

Arguments:
    SUPERVISOR_ID       Supervisor ID（例: SUPERVISOR_001）

Options:
    --title TITLE       タイトル（必須）
    --desc DESCRIPTION  説明（任意）
    --priority PRIORITY 優先度（High/Medium/Low、デフォルト: Medium）
    --json              JSON形式で出力

Example:
    python backend/xbacklog/add.py SUPERVISOR_001 --title "データエクスポート機能"
    python backend/xbacklog/add.py SUPERVISOR_001 --title "パフォーマンス改善" --priority High
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


# 有効な優先度値
VALID_PRIORITIES = ('High', 'Medium', 'Low')

# XBACKLOG IDのパターン
XBACKLOG_ID_PATTERN = re.compile(r'^XBACKLOG_\d{3}$')


def supervisor_exists(supervisor_id: str) -> bool:
    """Supervisorが存在するか確認"""
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


def get_next_xbacklog_id() -> str:
    """
    次のXBACKLOG IDを取得

    Returns:
        次のXBACKLOG ID（例: XBACKLOG_001）
    """
    conn = get_connection()
    try:
        result = fetch_one(
            conn,
            """
            SELECT id FROM cross_project_backlog
            WHERE id LIKE 'XBACKLOG_%'
            ORDER BY id DESC LIMIT 1
            """
        )

        if result:
            current_num = int(result['id'].split('_')[1])
            return f"XBACKLOG_{current_num + 1:03d}"
        else:
            return "XBACKLOG_001"
    finally:
        conn.close()


def add_xbacklog(
    supervisor_id: str,
    *,
    title: str,
    description: Optional[str] = None,
    priority: str = "Medium",
) -> Dict[str, Any]:
    """
    横断バックログを追加

    Args:
        supervisor_id: Supervisor ID（必須）
        title: タイトル（必須）
        description: 説明（任意）
        priority: 優先度（デフォルト: Medium）

    Returns:
        作成された横断バックログ情報

    Raises:
        ValidationError: 入力検証エラー
        DatabaseError: DB操作エラー
    """
    # バリデーション
    if not supervisor_id:
        raise ValidationError("Supervisor IDは必須です")

    if not supervisor_exists(supervisor_id):
        raise ValidationError(f"Supervisor '{supervisor_id}' が見つかりません")

    if not title:
        raise ValidationError("タイトルは必須です")

    if priority not in VALID_PRIORITIES:
        raise ValidationError(
            f"無効な優先度: {priority}. "
            f"有効な値: {', '.join(VALID_PRIORITIES)}"
        )

    # ID採番
    xbacklog_id = get_next_xbacklog_id()
    now = datetime.now().isoformat()

    conn = get_connection()
    try:
        execute_query(
            conn,
            """
            INSERT INTO cross_project_backlog
            (id, supervisor_id, title, description, priority, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?)
            """,
            (xbacklog_id, supervisor_id, title, description, priority, now, now)
        )
        conn.commit()

        # 作成したデータを取得して返す
        result = fetch_one(
            conn,
            """
            SELECT id, supervisor_id, title, description, priority, status,
                   assigned_project_id, assigned_backlog_id, analysis_result,
                   created_at, updated_at
            FROM cross_project_backlog WHERE id = ?
            """,
            (xbacklog_id,)
        )

        if result:
            return dict(result)
        else:
            raise DatabaseError("横断バックログの作成に失敗しました")

    except Exception as e:
        conn.rollback()
        if isinstance(e, (ValidationError, DatabaseError)):
            raise
        raise DatabaseError(f"横断バックログ作成エラー: {e}")
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
        description="横断バックログを追加",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("supervisor_id", help="Supervisor ID")
    parser.add_argument("--title", required=True, help="タイトル（必須）")
    parser.add_argument("--desc", dest="description", help="説明（任意）")
    parser.add_argument("--priority", default="Medium",
                        choices=VALID_PRIORITIES,
                        help="優先度（デフォルト: Medium）")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    try:
        xbacklog = add_xbacklog(
            args.supervisor_id,
            title=args.title,
            description=args.description,
            priority=args.priority,
        )

        if args.json:
            print(json.dumps(xbacklog, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"横断バックログ '{xbacklog['id']}' を追加しました。")
            print(f"  ID: {xbacklog['id']}")
            print(f"  Supervisor: {xbacklog['supervisor_id']}")
            print(f"  タイトル: {xbacklog['title']}")
            if xbacklog.get('description'):
                print(f"  説明: {xbacklog['description']}")
            print(f"  優先度: {xbacklog['priority']}")
            print(f"  ステータス: {xbacklog['status']}")

    except (ValidationError, DatabaseError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
